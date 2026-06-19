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
               backtest: null, btLoading: false };
  let GL = {};         // legacy-shaped map: slug -> {name, short, long, ...}
  let GROUPS = {};     // category -> display group

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
    if (p.has("view")) _S.view = p.get("view");
    if (p.has("cat")) _S.cat = p.get("cat");
    if (p.has("q")) _S.q = p.get("q");
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

  function entryCard(slug, e, expanded) {
    const altNames = (e.aliases || []).filter(a => a !== e.name && a.includes(" "));
    const fullName = altNames.length ? altNames.sort((a, b) => b.length - a.length)[0] : "";
    const more = [];
    if (e.long) more.push(`<div class="gl-meth">${e.long.split("\n\n").map(p => `<p>${escapeHtml(p)}</p>`).join("")}</div>`);
    if (e.formula) more.push(`<div class="gp-formula">${escapeHtml(e.formula)}</div>`);
    if (e.example) more.push(`<div class="gl-example"><span class="gl-microlabel">Example · </span>${escapeHtml(e.example)}</div>`);
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
        <span class="gl-badges">${moduleBadges(e)}</span>
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
      counts.all++;
      counts[grp] = (counts[grp] || 0) + 1;
      if (byGroup.has(grp)) byGroup.get(grp).push([slug, e]);
    }
    const chips = [`<button class="chip${_S.cat === "all" ? " active" : ""}" data-gl-cat="all">All <span class="gl-count">${counts.all}</span></button>`]
      .concat(groups.map(g =>
        `<button class="chip${_S.cat === g ? " active" : ""}" data-gl-cat="${escapeHtml(g)}">${escapeHtml(g)} <span class="gl-count">${counts[g] || 0}</span></button>`));
    document.getElementById("gl-cats").innerHTML = chips.join("");
    document.querySelectorAll("[data-gl-cat]").forEach(b => b.onclick = () => {
      _S.cat = b.dataset.glCat; syncToURL(); render();
    });
    // entries: alphabetical within the active scope
    const active = _S.cat === "all" ? groups : [_S.cat];
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
                  methodology: "methodology-body", "source-comparison": "source-comparison-body" };
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
const _RATER_META = {
  fangraphs:        { label: "FanGraphs",        color: "var(--neon-cyan)" },
  mlb_pipeline:     { label: "MLB Pipeline",     color: "var(--neon-amber)" },
  prospx_consensus: { label: "PROSPX consensus", color: "var(--up)" },
};
const _TIER_ORDER = ["<45", "45", "50", "55", "60+"];
function _raterMeta(r) {
  return _RATER_META[r] || { label: String(r), color: "var(--text-tertiary)" };
}
function _methProseHTML() {
  return `
  <div class="meth-prose">
    <h2 class="meth-h">How the consensus FV is built</h2>
    <p>Every source that publishes an explicit 20–80 Future Value grade contributes
    <strong>equally</strong> - there is no per-source weighting. The consensus FV is the
    mean of those published grades (FanGraphs, ESPN, Just Baseball, TJStats, MLB Pipeline,
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
      <dd>A wRC+-style index of organizational development: an org's cumulative FV growth over a
      1 / 3 / 6-year window scored against the league-mean farm (100 = mean, +10 = one standard
      deviation). Acquisitions are nullified and graduations don't subtract, so it measures only
      development of prospects already in the system. The farm grade weights 6y / 3y / 1y at
      60 / 30 / 10%.</dd>

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
      <div class="meth-eg-title">Worked examples · current board</div>
      <div class="meth-eg-row"><b>Jesus Made</b> - SS · MIL · ${gTermLink("fv", "FV")} 62. ${gTermLink("dvm_plus", "$DvM+")} 109.6 (projected surplus dollars ~10% above the mean farm's development pace), ${gTermLink("k_pct", "K%")} 14.3 / ${gTermLink("bb_pct", "BB%")} 10.7, ${gTermLink("ops_plus", "OPS+ vs lvl")} 115 → published ${gTermLink("surplus_value", "surplus value")} <b>$154M</b>.</div>
      <div class="meth-eg-row"><b>Seth Hernandez</b> - SP · PIT · ${gTermLink("fv", "FV")} 60. ${gTermLink("k_bb_pct", "K-BB%")} 18.0 (36.1 K − 18.1 BB), ${gTermLink("dvm_plus", "$DvM+")} 116.9 → published ${gTermLink("surplus_value", "surplus value")} <b>$131M</b>.</div>
      <div class="meth-eg-note">Live figures from this month's board - the same numbers shown on each player's card.</div>
    </div>

    <h2 class="meth-h">Surplus value - the economic model</h2>
    <p>A prospect is an asset because the six years of team control after debut are paid below
    market. Surplus value is the dollar production those controlled years are expected to deliver
    above what they cost:</p>
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
    formula, so each letter is auditable down to its leaves. Four branches:
    <strong>Development</strong> (40% - per-tool growth of prospects the org already had, ${gTermLink("dvm_plus", "DvM+")} /
    ${gTermLink("tools_dvm_plus", "ToolDvM+")}), <strong>MLB Production</strong> (25% - does the system produce
    big-leaguers, boom/bust rates, top-3 graduate WAR, a star-presence ${gTermLink("mlb_production_conviction", "Conviction")}
    flag), <strong>Acquisition Strategy</strong> (Draft / IFA / Trade / Waiver channels), and
    <strong>Financial</strong> (capital efficiency - ${gTermLink("fin_war_per_m", "WAR per $M")},
    ${gTermLink("fin_contract_surplus", "grad-contract surplus")}, ${gTermLink("fin_dollar_dvm", "Org $DvM+")},
    ${gTermLink("fin_draft_pool_efficiency", "draft-pool efficiency")}, ${gTermLink("fin_ifa_roi", "IFA ROI")}).
    Every leaf is z-scored across the 30 orgs and anchored so the composite reads on a 100 = league-mean
    scale; sparse leaves return " - " rather than guessing. Surplus enters here twice - as realized capital
    efficiency (Financial) and as the development of surplus dollars (Org $DvM+).</p>

    <h2 class="meth-h">Aggregation - player level to farm level</h2>
    <p>Roll-ups are explicit, not implied. Org surplus is the sum of its active prospects' per-player
    surplus dollars (the authoritative engine aggregate, <code>_active_surplus_net_mm</code>); the farm
    list, the detail Surplus tile, and the Finances tab all read that one number. DvM+ / ToolDvM+
    aggregate per-tool development across the org's actives with acquisitions nullified (so a trade
    doesn't masquerade as development) and graduations not subtracted (so promoting a star doesn't read
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
      <li><strong>Performance &amp; tracked data:</strong> MLB Stats API (MLB + MiLB statlines), Baseball Savant (Statcast) where available for upper-level / debuted players.</li>
      <li><strong>Contracts &amp; bonuses:</strong> published MLB draft-pool and international bonus-pool figures; Spotrac for graduate contract/AAV data.</li>
      <li><strong>Framework anchors:</strong> the FanGraphs scouting primer (FV→WAR ranges) and public $/WAR estimates (tiered, rolling multi-year average). The surplus engine's outcome buckets and discount rate are documented in <code>value_framework.py</code>.</li>
    </ul>
    <p class="meth-note">All grades remain the property of their publishers; the site stores them to compute a consensus and does not redistribute source lists wholesale.</p>

    <h2 class="meth-h">Methodology changelog</h2>
    <ul class="meth-changelog">
      <li><span class="mc-date">2026-06</span> Historical backfill: ingested FanGraphs 2017–2020 boards (new-format CSVs) + MLB Pipeline 2017–2020 Top 100, each grade date-stamped to its year. The backtest's resolved-cohort window grew from 2021–2023 (3 base years) to 2017–2023 (7); the common scored set rose from ≈2,294 to ≈2,544 players. On the larger, further-resolved sample the consensus still outranks its best individual source (Spearman 0.31 vs 0.30; AUC 0.79 vs 0.78).</li>
      <li><span class="mc-date">2026-06</span> Surplus engine v38: FV→WAR anchor moved from a single peak-year projection to a flat 6-year-average table; side difference carried by the position multiplier. Farm list/detail surplus consolidated on the engine aggregate.</li>
      <li><span class="mc-date">2026-06</span> Glossary reorganized into Glossary / Methodology / Source Comparison; taxonomy regrouped (Arkmetrics · Statcast · Standard · Scouting · Economic · Farm · Site Features); Statcast input terms added.</li>
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
      <dd>Grades, Arkmetrics, farm grades, and the backtest refresh monthly; transactions, IL, roster status, debuts, and trades refresh daily. Each board honestly stamps its own cadence.</dd>
      <dt>What's the track record - and its limits?</dt>
      <dd>The evaluation window spans seven preseason base years (2017–2023): the 2017–2020 cohorts are fully resolved while 2021–2023 are still accruing WAR, and cumulative WAR is censored at today. Top FV tiers stay thin (n≈40–70), so their rates move on a few outcomes. The Source Comparison area lists sample sizes and these caveats in full rather than headlining an inflated number.</dd>
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
  const series = bt.raters.map(r => {
    const tmap = {}; (bt.cohorts[r].tiers || []).forEach(t => { tmap[t.tier] = t; });
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
    const emph = s.rater === "prospx_consensus";
    const dots = pts.map(p => `<circle cx="${p.x.toFixed(1)}" cy="${p.y.toFixed(1)}" r="${emph ? 3.5 : 2.5}" fill="${col}"/>`).join("");
    return `<path d="${d}" fill="none" stroke="${col}" stroke-width="${emph ? 2.6 : 1.6}" ${emph ? "" : 'stroke-dasharray="5,3"'} stroke-linecap="round"/>${dots}`;
  }).join("");
  const legend = bt.raters.map(r =>
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
  const metric = (key, label, lo, hi, fmt) => {
    const rows = bt.raters.map(r => ({ r, v: acc[r] ? acc[r][key] : null })).filter(x => x.v != null);
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
  const cvi = bt.accuracy.consensus_vs_inputs || {};
  const verdict = (cvi.spearman && cvi.spearman.consensus_wins && cvi.auc && cvi.auc.consensus_wins)
    ? `<p class="meth-verdict is-good">On the common set of ${bt.accuracy.common_n.toLocaleString()} players graded by all three, the <strong>PROSPX consensus edges out both individual inputs</strong> on ordering skill and discrimination - the result a consensus model needs to defend. The margin is modest and not uniform year-to-year; see the caveats.</p>`
    : `<p class="meth-verdict">On the common set of ${bt.accuracy.common_n.toLocaleString()} players, the consensus is competitive with its inputs but does not lead on every metric - reported honestly rather than cherry-picked.</p>`;
  return `<div class="meth-chart meth-accuracy">
    <div class="meth-chart-title">Head-to-head predictive accuracy <span class="meth-sub">same players, same outcome, same window</span></div>
    ${sp}${au}${verdict}
  </div>`;
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
  const raters = bt.raters;
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
    <p class="meth-note">Where the consensus leads (5 of 6 archetypes), the blend is the safe default. The one place a single source wins outright is <strong>college arms, where MLB Pipeline is best</strong> and FanGraphs grades pitching weakest. International arms are the hardest archetype to grade, with AUC barely above a coin flip.</p>
  </div>`;
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
      "The org letter grade is a weighted tree: Development, MLB Production, Acquisition Strategy, and Financial branches, each built from auditable leaves."),
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
  const today = new Date().toLocaleDateString("en-US", { year: "numeric", month: "long", day: "numeric" });
  const printHead = `<div id="methodology-print-head">eephus.io - Methodology · eephus.io/glossary · ${escapeHtml(today)}</div>`;
  const toolbar = `<div class="meth-toolbar"><button class="meth-export-btn" type="button" onclick="_printMethodology()" title="Print or save the methodology as a PDF">⎙ Export methodology (PDF)</button></div>`;
  el.innerHTML = printHead + toolbar + _methProseHTML() + _methRegistryHTML() + _methInteractivesHTML();
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
      return `<tr>
        <td><strong>${escapeHtml(m.model_id)}</strong><br><span class="meth-note">${escapeHtml(m.surface || "")}</span></td>
        <td>${escapeHtml(m.champion || "")}</td>
        <td>${escapeHtml(m.baseline || "")}</td>
        <td>${_REG_VERDICT_GLYPH[m.verdict] || escapeHtml(m.verdict || "")}</td>
        <td>${art}</td>
      </tr>`;
    }).join("");
    body = `
      <p class="meth-note">Every predictive model on the platform, with an honest verdict and its committed eval artifact. <strong>${counts.validated || 0} validated · ${counts.provisional || 0} provisional · ${counts.unvalidated || 0} unvalidated · ${counts.deprecated || 0} deprecated</strong>${reg.checked_at ? ` · last checked ${escapeHtml(reg.checked_at)}` : ""}. Unvalidated rows are listed precisely so they can't hide; losing challengers stay committed.</p>
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
// Part 8 - exportable methodology: print just the methodology body (the
// toolbar + interactive widgets are hidden by the print stylesheet; a dated
// PROSPX header prints at the top). Users "Save as PDF" from the print dialog.
function _printMethodology() {
  document.body.classList.add("printing-meth");
  const cleanup = () => { document.body.classList.remove("printing-meth"); window.removeEventListener("afterprint", cleanup); };
  window.addEventListener("afterprint", cleanup);
  setTimeout(() => { window.print(); }, 30);
  // Fallback cleanup if afterprint doesn't fire (some browsers).
  setTimeout(cleanup, 1500);
}

// Source Comparison - the empirical backtest, visually set apart from the
// methodology prose as the "does it work?" evidence area (distinct framed
// container + eyebrow). Lazy-loads source_backtest.json.
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
      <h2 class="meth-h">Does the consensus outperform its sources?</h2>
      <p class="meth-window">${escapeHtml(bt.window.note)} <strong>Sources with too little history to score</strong> (${(bt.insufficient_history || []).join(", ")}) are excluded, not guessed at.</p>
      ${_methAccuracyChart(bt)}
      <h3 class="meth-h3">Best grader by prospect archetype</h3>
      ${_methArchetypeTable(bt)}
      <div class="meth-chart-grid">
        ${_methCalibrationChart(bt, "mean_war", "Mean career WAR")}
        ${_methCalibrationChart(bt, "contributor_rate", "Contributor rate (career WAR ≥ " + (od.contributor_war ?? 3) + ")", { pct: true, yMax: 1 })}
      </div>
      <h3 class="meth-h3">Cohort outcomes by FV tier</h3>
      <p class="meth-note">Every prospect a source graded that preseason is in its cohort - players who never debuted stay in at 0 WAR (no survivorship cherry-picking). Cumulative WAR is censored at today, so younger cohorts (2023) have had less time to accrue it; the rate columns (WAR/yr, Reg pace) are less sensitive to that.</p>
      <div class="meth-tables">${bt.raters.map(r => _methTierTable(bt, r)).join("")}</div>
      <div class="meth-caveats">
        <div class="meth-caveats-title">⚠ Read this honestly</div>
        <ul>
          <li><strong>Short track record.</strong> Only ${bt.window.years.length} preseason base years (${bt.window.years.join(", ")}) are old enough to have resolved outcomes. The newer sources have <em>zero</em> resolved cohorts.</li>
          <li><strong>Thin top tiers.</strong> The 60+ tier is only n≈40–60 across all years - a handful of hits or misses moves its rates a lot.</li>
          <li><strong>Censoring.</strong> Outcomes are cumulative WAR as of ${escapeHtml(bt.as_of_date || "today")}; the 2023 cohort has had ~3 seasons, the 2021 cohort ~5. Rate metrics mitigate but don't erase this.</li>
          <li><strong>Modest, noisy edge.</strong> The consensus's advantage over its best input is real on the pooled set but small, and it isn't #1 every single year. A credible short track record beats an inflated one.</li>
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

})();
