/* Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
 * Unauthorized copying of this file, via any medium is strictly prohibited
 * Proprietary and confidential
 * Written by Noah J. Dengler (@ARKNDJL), 2026 */

// =============================================================================
// eephus.io Free Agency app (/fa/) — Class Board / Team Fits / Archive /
// Model Accountability / Glossary
// =============================================================================
// A standalone surface, SEPARATE from PROSPX by design: it shares the site
// chrome (assets/site.css) and the data/ directory but loads none of the
// PROSPX boot payload and none of its script. Fed by the three fa_export.py
// sidecars (fa_class.json / fa_archive.json / fa_meta.json) fetched directly
// from /data/. Two numbers, never conflated: RATIONAL VALUE (NPV of the gated
// projection) vs PREDICTED MARKET (mYears/mGuarantee/mAAV with bands).
// Contract Surplus ($) = rational − predicted; Deal+ 100 = market-rate.
(function () {
  "use strict";

  const EM_DASH = "—";
  const D = {};            // loaded sidecars by name
  const _inflight = {};

  // Mirror of PROSPX's formatMetric for the types this surface renders —
  // same precision rules, same null token, same -0 collapse. Kept local so
  // the FA page never imports PROSPX script.
  function formatMetric(value, type = "int") {
    const n = Number(value);
    if (value == null || value === "" || !Number.isFinite(n)) return EM_DASH;
    const z = n === 0 ? 0 : n;                       // collapse -0 -> 0
    const sign = z > 0 ? "+" : (z < 0 ? "-" : "");   // zero is unsigned
    const abs = Math.abs(z);
    switch (type) {
      case "int":      return String(Math.round(z));
      case "war":      return z.toFixed(1);
      case "rate":     return sign + abs.toFixed(2);
      case "surplusM": return sign + "$" + abs.toFixed(1) + "M";
      case "moneyM":   return "$" + (abs >= 100 ? abs.toFixed(0) : abs.toFixed(1)) + "M";
      case "pct":      return z.toFixed(1) + "%";
      default:         return String(z);
    }
  }

  function money(usd, type = "moneyM") {
    return usd == null ? EM_DASH : formatMetric(usd / 1e6, type);
  }

  function esc(s) {
    return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  function load(name) {
    if (D[name]) return Promise.resolve(D[name]);
    if (_inflight[name]) return _inflight[name];
    _inflight[name] = fetch(`/data/${name}.json`, { cache: "no-cache" })
      .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
      .then(payload => { D[name] = payload; return payload; })
      .finally(() => { delete _inflight[name]; });
    return _inflight[name];
  }

  // ---- URL state (#view=board|fits|archive|model|glossary&team=&winter=) ----
  const VIEWS = [["board", "Class Board"], ["fits", "Team Fits"],
                 ["archive", "Archive"], ["model", "Model Accountability"],
                 ["glossary", "Glossary"]];
  const state = { view: "board", team: null, winter: null };

  function syncFromURL() {
    const p = new URLSearchParams(window.location.hash.slice(1));
    if (p.has("view") && VIEWS.some(([k]) => k === p.get("view"))) state.view = p.get("view");
    if (p.has("team")) state.team = p.get("team");
    if (p.has("winter")) state.winter = Number(p.get("winter")) || null;
  }

  function syncToURL() {
    const p = new URLSearchParams();
    if (state.view !== "board") p.set("view", state.view);
    if (state.view === "fits" && state.team) p.set("team", state.team);
    if (state.view === "archive" && state.winter) p.set("winter", String(state.winter));
    const h = p.toString();
    history.replaceState(null, "", h ? `#${h}` : window.location.pathname);
  }

  async function render() {
    const rows = document.getElementById("fa-rows");
    const chips = document.getElementById("fa-view-chips");
    const banner = document.getElementById("fa-banner");
    if (!rows) return;
    chips.innerHTML = VIEWS.map(([k, label]) =>
      `<button class="chip${state.view === k ? " active" : ""}" data-fa-view="${k}">${label}</button>`).join("");
    chips.querySelectorAll("[data-fa-view]").forEach(b => b.onclick = () => {
      state.view = b.dataset.faView; syncToURL(); render();
    });
    rows.innerHTML = `<div class="state-message is-loading">Loading free-agency data&hellip;</div>`;
    try {
      await Promise.all([load("fa_class"), load("fa_archive"), load("fa_meta")]);
    } catch (e) {
      rows.innerHTML = `<div class="state-message is-error">Free-agency data unavailable
        (${esc(String(e.message || e))}). Run <code>python fa_export.py</code> to regenerate
        <code>data/fa_*.json</code>.</div>`;
      return;
    }
    const cls = D.fa_class, meta = D.fa_meta;
    if (!cls || !cls.members) {
      rows.innerHTML = `<div class="state-message">Free-agency data not exported yet.</div>`;
      return;
    }
    banner.innerHTML = cls.cba_carry_forward
      ? `<div class="fa-cba-note" title="The 2022 CBA expired 2026-12-01. Every 2027 threshold/QO figure is a carry-forward of the last known rule, not a published number.">&#9888; CBA rules past 2026-12-01 are carried forward &mdash; thresholds and QO values for this winter are NOT yet collectively bargained.</div>`
      : "";
    if (state.view === "board") renderBoard(rows, cls);
    else if (state.view === "fits") renderFits(rows, cls, meta);
    else if (state.view === "archive") renderArchive(rows);
    else if (state.view === "model") renderModel(rows, meta);
    else renderGlossary(rows);
  }

  function statusChip(m) {
    if (m.status === "locked") return `<span title="Contract expires — locked into the class.">UFA</span>`;
    const pct = m.enterProb != null ? ` &middot; P(enter) ${(m.enterProb * 100).toFixed(0)}%` : "";
    const price = m.optPrice ? ` $${(m.optPrice / 1e6).toFixed(1)}M` : "";
    return `<span title="Option-pending — class membership is probabilistic until the option resolves. Exercise probability is a documented v1 heuristic.">${esc((m.type || "").replace(/_/g, " "))}${price}${pct}</span>`;
  }

  function renderBoard(rows, cls) {
    const members = cls.members;
    const head = `<div class="newsprint-eyebrow" style="margin-top:4px;">
      <span class="newsprint-eyebrow-label">2026-27 Class Board</span>
      <span class="newsprint-eyebrow-meta">${members.length} constructed members &middot; ${cls.n_projected} projected &middot; winter $/WAR (ex-ante) ${money(cls.dpw_usd)} &middot; sorted by mGuarantee</span>
    </div>`;
    const body = members.map((m, i) => {
      const fits = (m.fits || []).map(f =>
        `<span title="fit ${f.fit} — need ${f.need} / window ${f.window} / afford ${f.afford} / park ${f.park} / behavior ${f.behavior}${f.blockedBy ? " — blocked by " + esc(f.blockedBy.join(", ")) : ""}">${f.org}${f.blockedBy ? "*" : ""}</span>`).join(" ");
      const comps = (m.comps || []).map(c =>
        `${esc(c.name)} '${String(c.yr).slice(2)} ${c.years || "?"}y/${c.guar ? "$" + (c.guar / 1e6).toFixed(0) + "M" : "?"}`).join("; ");
      const yearsBand = m.mYears != null
        ? `${m.mYears}<span class="fa-band"> (${m.mYearsP10 ?? "?"}&ndash;${m.mYearsP90 ?? "?"})</span>` : EM_DASH;
      const guarBand = m.mGuar != null
        ? `${money(m.mGuar)}<span class="fa-band"> (${money(m.mGuarP10)}&ndash;${money(m.mGuarP90)})</span>` : EM_DASH;
      const surplus = m.surplus != null ? formatMetric(m.surplus / 1e6, "surplusM") : EM_DASH;
      return `<tr${m.mGuar == null ? ' class="fa-dim"' : ""}>
        <td>${i + 1}</td>
        <td><strong>${esc(m.name)}</strong><span class="fa-sub"> ${esc(m.pos || "")} &middot; ${m.age != null ? Math.floor(m.age) : "?"} &middot; ${esc(m.from || "")}</span>${comps ? `<div class="fa-comps" title="Nearest real historical contracts (never fabricated)">comps: ${comps}</div>` : ""}</td>
        <td>${statusChip(m)}</td>
        <td title="Projected year-1 bWAR from the Gate-1-passed engine">${m.warY1 != null ? formatMetric(m.warY1, "war") : EM_DASH}</td>
        <td title="Predicted contract length (P10–P90 band)">${yearsBand}</td>
        <td title="Predicted total guarantee (P10–P90 band)">${guarBand}</td>
        <td title="Predicted AAV">${m.mAav != null ? money(m.mAav) : EM_DASH}</td>
        <td title="Rational value — NPV of the projected WAR path at the platform 9% discount">${m.rational != null ? money(m.rational) : EM_DASH}</td>
        <td title="Contract Surplus ($) — rational value minus predicted price">${surplus}</td>
        <td title="Deal+ — 100 = market-rate; above 100 = team-friendly at the predicted price">${m.dealPlus ?? EM_DASH}</td>
        <td title="Top team fits (* = position blocked by a PROSPX prospect)">${fits || EM_DASH}</td>
      </tr>`;
    }).join("");
    rows.innerHTML = head + `<table class="detail-table">
      <thead><tr><th>#</th><th>Player</th><th>Status</th><th>WAR y1</th><th>mYears</th><th>mGuarantee</th><th>mAAV</th><th>Rational</th><th>Surplus</th><th>Deal+</th><th>Fits</th></tr></thead>
      <tbody>${body}</tbody></table>`;
  }

  function renderFits(rows, cls, meta) {
    // teamFits covers ALL 30 orgs (top-12 each, members referenced by index);
    // fall back to aggregating the members' own top-3 fits on older exports.
    const byOrg = {};
    if (cls.teamFits) {
      Object.entries(cls.teamFits).forEach(([org, list]) => {
        byOrg[org] = list.map(f => ({ m: cls.members[f.i], f }));
      });
    } else {
      cls.members.forEach(m => (m.fits || []).forEach(f => {
        (byOrg[f.org] = byOrg[f.org] || []).push({ m, f });
      }));
    }
    const orgs = Object.keys(byOrg).sort();
    if (!state.team || !byOrg[state.team]) state.team = orgs[0];
    const chips = orgs.map(o =>
      `<button class="chip${o === state.team ? " active" : ""}" data-fa-team="${o}">${o}</button>`).join("");
    const t = (meta && meta.teams && meta.teams[state.team]) || {};
    const list = (byOrg[state.team] || []).sort((a, b) => b.f.fit - a.f.fit);
    const body = list.map(({ m, f }) => `<tr>
        <td><strong>${esc(m.name)}</strong> <span class="fa-sub">${esc(m.pos || "")} &middot; ${m.age != null ? Math.floor(m.age) : "?"}</span></td>
        <td>${f.fit.toFixed(2)}</td>
        <td>${f.need}</td><td>${f.window}</td><td>${f.afford}</td><td>${f.park}</td><td>${f.behavior}</td>
        <td>${f.blockedBy ? `<span title="Position blocked by a PROSPX prospect (FV &ge; 50, near ETA)">${esc(f.blockedBy.join(", "))}</span>` : EM_DASH}</td>
        <td>${m.mGuar != null ? `${m.mYears}y / ${money(m.mGuar)}` : EM_DASH}</td>
      </tr>`).join("");
    rows.innerHTML = `<div class="filter-bar"><span class="filter-label">Team</span>${chips}</div>
      <div class="newsprint-eyebrow" style="margin-top:2px;"><span class="newsprint-eyebrow-label">${state.team} fits</span>
      <span class="newsprint-eyebrow-meta">committed ${money(t.committed)} &middot; CBT space ${t.space != null ? formatMetric(t.space / 1e6, "surplusM") : EM_DASH} &middot; baseline ${t.baseWins ?? "?"}w (contracted core) &middot; biggest deal ever ${money(t.maxGuar)}</span></div>
      <table class="detail-table">
      <thead><tr><th>Player</th><th>Fit</th><th>Need</th><th>Window</th><th>Afford</th><th>Park</th><th>Behavior</th><th>Blocked by</th><th>Predicted</th></tr></thead>
      <tbody>${body || `<tr><td colspan="9">No scored fits for ${state.team} in this class.</td></tr>`}</tbody></table>`;
    rows.querySelectorAll("[data-fa-team]").forEach(b => b.onclick = () => {
      state.team = b.dataset.faTeam; syncToURL(); render();
    });
  }

  function renderArchive(rows) {
    const arc = D.fa_archive;
    if (!arc || !arc.winters) {
      rows.innerHTML = `<div class="state-message">Archive not exported yet.</div>`;
      return;
    }
    const winters = arc.winters.slice().sort((a, b) => b.year - a.year);
    if (!state.winter || !winters.some(w => w.year === state.winter)) state.winter = winters[0].year;
    const chips = winters.map(w =>
      `<button class="chip${w.year === state.winter ? " active" : ""}" data-fa-winter="${w.year}">${w.year - 1}-${String(w.year).slice(2)}</button>`).join("");
    const w = winters.find(x => x.year === state.winter);
    const body = w.signings.map(s => `<tr${s.milb ? ' class="fa-dim"' : ""}>
        <td><strong>${esc(s.name)}</strong> <span class="fa-sub">${esc(s.pos || "")}</span>${s.qo ? ' <span title="Received a qualifying offer">QO</span>' : ""}</td>
        <td>${esc(s.from || "")} &rarr; ${esc(s.to || "")}</td>
        <td>${s.years ?? EM_DASH}</td>
        <td>${s.milb ? "MiLB deal" : money(s.guar)}</td>
        <td>${money(s.aav)}</td>
        <td title="Realized bWAR over the contract's elapsed seasons">${s.warTd != null ? formatMetric(s.warTd, "war") : EM_DASH}</td>
        <td title="Realized surplus to date: WAR delivered x that season's estimated $/WAR minus prorated money paid">${s.surplusTd != null ? formatMetric(s.surplusTd / 1e6, "surplusM") : EM_DASH}</td>
        <td>${s.done ? "complete" : (s.warTd != null ? "running" : EM_DASH)}</td>
      </tr>`).join("");
    rows.innerHTML = `<div class="filter-bar"><span class="filter-label">Winter</span>${chips}</div>
      <div class="newsprint-eyebrow" style="margin-top:2px;"><span class="newsprint-eyebrow-label">${state.winter - 1}-${String(state.winter).slice(2)} winter</span>
      <span class="newsprint-eyebrow-meta">${w.n} signings &middot; ${money(w.spend_usd)} guaranteed &middot; implied $/WAR ${money(w.dpw_usd)}${w.qo_offered != null ? ` &middot; ${w.qo_offered} qualifying offers` : ""}</span></div>
      <table class="detail-table">
      <thead><tr><th>Player</th><th>From &rarr; To</th><th>Yrs</th><th>Guarantee</th><th>AAV</th><th>WAR to date</th><th>Surplus to date</th><th>Status</th></tr></thead>
      <tbody>${body}</tbody></table>`;
    rows.querySelectorAll("[data-fa-winter]").forEach(b => b.onclick = () => {
      state.winter = Number(b.dataset.faWinter); syncToURL(); render();
    });
  }

  function renderModel(rows, meta) {
    if (!meta || (!meta.gate1 && !meta.gate2)) {
      rows.innerHTML = `<div class="state-message">Model evaluation artifacts not exported yet.</div>`;
      return;
    }
    const g1 = meta.gate1, g2 = meta.gate2;
    const pooledRows = (pooled, fmt) => Object.entries(pooled).map(([k, v]) =>
      `<tr><td>${esc(k)}</td><td>${fmt(v.mae_model)}</td><td>${fmt(v.mae_base)}</td><td>${v.n}</td><td>${v.mae_model < v.mae_base ? "&#10003; beats baseline" : "&#10007; behind baseline"}</td></tr>`).join("");
    const missRows = g2 && g2.biggest_misses ? g2.biggest_misses.map(m =>
      `<tr><td>${m.winter}</td><td>${esc(m.player)}</td><td>${esc(m.to_team || "")}</td>
       <td>${m.actual_years}y / $${m.actual_guar_mm}M</td><td>${m.pred_years}y / $${m.pred_guar_mm}M</td>
       <td>${formatMetric(m.err_mm, "rate")}M</td></tr>`).join("") : "";
    rows.innerHTML = `
      <div class="newsprint-eyebrow"><span class="newsprint-eyebrow-label">Model Accountability</span>
      <span class="newsprint-eyebrow-meta">both hard gates, rendered verbatim from the committed eval artifacts &mdash; misses and all &middot; ${meta.cba ? meta.cba.unverified_records + " curated CBA records pending owner verification" : ""}</span></div>
      ${g1 ? `<h3>Gate 1 &mdash; projection engine (${g1.pass ? "PASSED" : "FAILING"})</h3>
      <div class="fa-note">train &le; N&minus;1, predict N, ten held-out seasons ${g1.targets ? g1.targets.join(", ") : ""} &middot; P10&ndash;P90 coverage ${g1.coverage_p10_p90 != null ? g1.coverage_p10_p90.toFixed(3) : "?"} (target 0.75&ndash;0.85)</div>
      <table class="detail-table"><thead><tr><th>Metric</th><th>Model MAE</th><th>Naive baseline</th><th>n</th><th>Verdict</th></tr></thead>
      <tbody>${pooledRows(g1.pooled, v => v == null ? EM_DASH : v.toFixed(3))}</tbody></table>` : ""}
      ${g2 ? `<h3>Gate 2 &mdash; market model (${g2.pass ? "PASSED" : "FAILING"})</h3>
      <div class="fa-note">forward-chained winters ${g2.test_winters ? g2.test_winters.join(", ") : ""} vs nearest-comps baseline &middot; guarantee/AAV in $M</div>
      <table class="detail-table"><thead><tr><th>Metric</th><th>Model MAE</th><th>Comps baseline</th><th>n</th><th>Verdict</th></tr></thead>
      <tbody>${pooledRows(g2.pooled, v => v == null ? EM_DASH : v.toFixed(2))}</tbody></table>
      <h3>Biggest misses (published, not hidden)</h3>
      <table class="detail-table"><thead><tr><th>Winter</th><th>Player</th><th>To</th><th>Actual</th><th>Model</th><th>Err</th></tr></thead>
      <tbody>${missRows}</tbody></table>
      <div class="fa-note" style="margin-top:8px;">${(g2.notes || []).map(esc).join(" &middot; ")}</div>` : ""}`;
  }

  // ---- Glossary — the module's six terms, moved here from the PROSPX
  // glossary when Free Agency became its own surface. -------------------------
  const GLOSSARY = [
    ["mGuarantee",
     "Predicted total contract guarantee for a free agent, from the market model (what teams WILL pay, not what the production is worth).",
     "mGuarantee is the market model: a transparent two-stage regression (contract length first, then log-guarantee given length) trained only on the 2014-15 to present FA-signing corpus, with age, projected year-1 bWAR, position group, qualifying-offer status, class supply, the winter $/WAR level (carried forward ex-ante), nearest-comps anchors, and economic anchors (discounted projected WAR x $/WAR; prime-years x quality). Predictions clamp to a 2.5x envelope around the comps median and blend toward comps in the megadeal regime. P10-P90 bands are empirical residual quantiles from the forward-chained backtest. The model beat the nearest-comps baseline on guarantee, AAV and years across nine held-out winters (Gate 2 on the Model Accountability page)."],
    ["mAAV",
     "Predicted average annual value: mGuarantee / mYears, with its own P10-P90 band.",
     "Both framings of a contract are projected: the per-year price (mAAV) and the total value / length (mGuarantee / mYears). mAAV bands ride the guarantee band at the point-estimate term."],
    ["mYears",
     "Predicted contract length (P10-P90 banded), from a log-years model with comps stacking.",
     "Contract length is modeled before money (teams trade years against AAV). The stage predicts log(years) with curvature terms (WAR squared, age x WAR) and the nearest-comps median length stacked as a feature; it beat the comps baseline 0.448 vs 0.485 MAE across nine held-out winters."],
    ["Deal+",
     "Contract-value index: 100 = priced exactly at rational value; above 100 = team-friendly.",
     "Deal+ = 100 x rational value / predicted (or actual) guarantee. Rational value is the NPV of the projected WAR path (aging-curve decayed, playing-time weighted) x escalated $/WAR at the platform 9% discount rate - the same NPV currency as PROSPX prospect surplus, so the qualifying-offer pick tax can be subtracted meaningfully."],
    ["Contract Surplus ($)",
     "Rational value minus predicted market price - the gap the module exists to surface.",
     "Two independently derived numbers, never conflated: RATIONAL VALUE (what the projected production is worth in NPV) and PREDICTED MARKET PRICE (what teams will actually pay, from the market model). Contract Surplus ($) is rational minus market. Positive = the market is expected to underprice the player. The retrospective ledger applies the same lens backward: realized bWAR x each season's estimated $/WAR minus prorated money paid, for every MLB free-agent deal since 2014-15."],
    ["QO pick tax",
     "The dollar cost of forfeited draft picks (and intl pool money) when signing a qualifying-offer free agent.",
     "Signing a QO-attached free agent forfeits draft picks per the CBA compensation matrix (rule-versioned; CBT payors forfeit their 2nd- and 5th-highest picks plus $1M of international pool). The module prices each forfeited slot using the platform's OWN draft research: median consensus FV at the slot mapped through the prospect surplus curve. Because rational value and pick values share the same 9% NPV currency, the tax subtracts directly."],
  ];

  function renderGlossary(rows) {
    rows.innerHTML = `<div class="newsprint-eyebrow"><span class="newsprint-eyebrow-label">Glossary</span>
      <span class="newsprint-eyebrow-meta">the module's terms &mdash; every number on this surface defined</span></div>`
      + GLOSSARY.map(([name, short, long]) => `<div class="fa-gloss">
        <h3>${esc(name)}</h3>
        <p class="fa-gloss-short">${esc(short)}</p>
        <p class="fa-gloss-long">${esc(long)}</p>
      </div>`).join("");
  }

  function boot() {
    syncFromURL();
    window.addEventListener("hashchange", () => { syncFromURL(); render(); });
    render();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
