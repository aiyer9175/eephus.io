/* Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
 * Unauthorized copying of this file, via any medium is strictly prohibited
 * Proprietary and confidential
 * Written by Noah J. Dengler (@ARKNDJL), 2026 */

// =============================================================================
// eephus.io MLB Projections app (/projections/)
// =============================================================================
// The FA module's Gate-1-validated projection engine applied to the whole
// league, plus PROSPX prospects joining at their projected ETA. One sidecar
// (data/mlb_projections.json, proj_export.py); standalone by design - no
// PROSPX boot payload, no FA sidecars. Every row carries floor/mean/ceiling
// probability buckets; veteran surplus exists ONLY on salary-known seasons.
(function () {
  "use strict";

  const EM_DASH = " - ";
  let DATA = null;

  function fmtWar(v) {
    if (v == null || !Number.isFinite(Number(v))) return EM_DASH;
    const z = Number(v) === 0 ? 0 : Number(v);
    return z.toFixed(1);
  }
  function money(usd) {
    if (usd == null) return EM_DASH;
    const m = usd / 1e6;
    const a = Math.abs(m);
    return (m < 0 ? "-$" : "$") + (a >= 100 ? a.toFixed(0) : a.toFixed(1)) + "M";
  }
  function esc(s) {
    return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  // ORG abbreviation -> ESPN logo slug (same map as build_site/prospx).
  const ESPN_SLUGS = {
    ARI: "ari", ATH: "ath", ATL: "atl", BAL: "bal", BOS: "bos",
    CHC: "chc", CHW: "chw", CIN: "cin", CLE: "cle", COL: "col",
    DET: "det", HOU: "hou", KCR: "kc", LAA: "laa", LAD: "lad",
    MIA: "mia", MIL: "mil", MIN: "min", NYM: "nym", NYY: "nyy",
    PHI: "phi", PIT: "pit", SDP: "sd", SEA: "sea", SFG: "sf",
    STL: "stl", TBR: "tb", TEX: "tex", TOR: "tor", WSN: "wsh",
  };
  function teamLogo(org) {
    if (!org) return "";
    const slug = ESPN_SLUGS[org] || String(org).toLowerCase();
    return `<img class="fa-logo" src="https://a.espncdn.com/i/teamlogos/mlb/500/${slug}.png" alt="${esc(org)}" loading="lazy" onerror="this.replaceWith('${esc(org)}')">`;
  }

  function posGroup(pos) {
    const head = String(pos || "").toUpperCase().split("/")[0].trim();
    if (["SP", "SP2", "P", "LHP", "RHP"].includes(head)) return "SP";
    if (["RP", "CL", "SIRP", "MIRP"].includes(head)) return "RP";
    if (head === "C") return "C";
    if (["1B", "2B", "3B", "SS", "IF"].includes(head)) return "IF";
    if (["LF", "CF", "RF", "OF"].includes(head)) return "OF";
    if (head === "DH" || head === "H") return "DH";
    return "IF";
  }

  // WAR heat class - color escalates with the season's own WAR.
  function warClass(w) {
    if (w == null) return "";
    if (w >= 4) return " proj-war-elite";
    if (w >= 2.5) return " proj-war-good";
    if (w >= 1) return " proj-war-avg";
    return " proj-war-low";
  }

  const state = { src: "all", pos: "all", team: "all", q: "", sort: "warTotal",
                  dir: -1, limit: 100 };

  function syncFromURL() {
    const p = new URLSearchParams(location.hash.slice(1));
    if (p.has("src")) state.src = p.get("src");
    if (p.has("pos")) state.pos = p.get("pos");
    if (p.has("team")) state.team = p.get("team");
    if (p.has("q")) state.q = p.get("q");
    if (p.has("sort")) state.sort = p.get("sort");
  }
  function syncToURL() {
    const p = new URLSearchParams();
    if (state.src !== "all") p.set("src", state.src);
    if (state.pos !== "all") p.set("pos", state.pos);
    if (state.team !== "all") p.set("team", state.team);
    if (state.q) p.set("q", state.q);
    if (state.sort !== "warTotal") p.set("sort", state.sort);
    const h = p.toString();
    history.replaceState(null, "", h ? `#${h}` : location.pathname);
  }

  // Season-aligned WAR for a row: vets start at first_season; prospects at
  // their ETA (pre-ETA seasons are MiLB time - rendered as such, never 0).
  function warAt(m, t) {
    if (m.src === "prospect") {
      const off = t - (m.eta - DATA.first_season);
      return off >= 0 && off < (m.war || []).length ? m.war[off] : null;
    }
    return (m.war || [])[t] ?? null;
  }
  function bandAt(m, t, which) {
    const arr = which === "lo" ? m.warP10 : m.warP90;
    if (!arr) return null;
    if (m.src === "prospect") {
      const off = t - (m.eta - DATA.first_season);
      return off >= 0 && off < arr.length ? arr[off] : null;
    }
    return arr[t] ?? null;
  }

  function rows() {
    const all = (DATA.vets || []).concat(DATA.prospects || []);
    const q = state.q.trim().toLowerCase();
    return all.filter(m =>
      (state.src === "all" || m.src === state.src)
      && (state.pos === "all" || posGroup(m.pos) === state.pos)
      && (state.team === "all" || m.team === state.team)
      && (!q || (m.name || "").toLowerCase().includes(q)));
  }

  function sortRows(list) {
    const k = state.sort;
    const val = m => {
      if (k === "age") return m.age ?? 99;
      if (k === "sur") return m.surNpv ?? -1e15;
      if (k.startsWith("y")) return warAt(m, Number(k.slice(1))) ?? -99;
      return m[k] ?? -99;
    };
    return list.slice().sort((a, b) => state.dir * (val(a) > val(b) ? 1 : val(a) < val(b) ? -1 : 0));
  }

  function tagFor(m) {
    if (m.src === "prospect") {
      return `<span class="proj-tag proj-tag-prospect" title="PROSPX prospect - outcome-model projection (P(bucket|FV) × calibrated trajectories) starting at the projected ETA. Floor/ceiling are the 10th/90th-percentile OUTCOME buckets (${esc(m.bucketLo || "?")} → ${esc(m.bucketHi || "?")}); P(bust) ${m.pBust != null ? (m.pBust * 100).toFixed(0) + "%" : "?"}.">FV ${m.fv} · ETA ${m.eta}</span>`;
    }
    return m.twoWay
      ? `<span class="proj-tag" title="Two-way profile - projected on the larger recent exposure only (disclosed simplification).">two-way</span>` : "";
  }

  function render() {
    const root = document.getElementById("proj-rows");
    const bar = document.getElementById("proj-filters");
    const banner = document.getElementById("proj-banner");
    if (!root || !DATA) return;
    const first = DATA.first_season;
    const teams = [...new Set((DATA.vets || []).map(m => m.team).filter(Boolean))].sort();

    banner.innerHTML = `<div class="fa-note fa-sources">
      ${DATA.n_vets} veterans (the <span data-gl="fa_projection_engine">FA projection engine</span>, league-wide)
      &middot; ${DATA.n_prospects} prospects (<span data-gl="proj_buckets">outcome buckets</span> from their PROSPX ETA)
      &middot; seasons priced at the ${first} ex-ante <span data-gl="winter_dpw">$/WAR</span> ${money(DATA.dpw_usd)},
      escalating ${(DATA.dpw_infl * 100).toFixed(0)}%/yr
      &middot; <span data-gl="contract_surplus">surplus</span> only where a real contract exists</div>`;

    const chip = (label, key, field) =>
      `<button class="chip${state[field] === key ? " active" : ""}" data-pf="${field}:${key}">${label}</button>`;
    bar.innerHTML = `<span class="filter-label">Source</span>
      ${chip("All", "all", "src")}${chip("Veterans", "vet", "src")}${chip("Prospects", "prospect", "src")}
      <span class="filter-label" style="margin-left:10px;">Pos</span>
      ${["all", "SP", "RP", "C", "IF", "OF", "DH"].map(p => chip(p === "all" ? "All" : p, p, "pos")).join("")}
      <span class="filter-label" style="margin-left:10px;">Team</span>
      <select id="proj-team" class="proj-select">
        <option value="all">All teams</option>
        ${teams.map(t => `<option value="${t}"${state.team === t ? " selected" : ""}>${t}</option>`).join("")}
      </select>
      <input id="proj-q" class="proj-search" type="search" placeholder="Search players…" value="${esc(state.q)}" aria-label="Search players">`;
    bar.querySelectorAll("[data-pf]").forEach(b => b.onclick = () => {
      const [field, key] = b.dataset.pf.split(":");
      state[field] = key; state.limit = 100; syncToURL(); render();
    });
    const sel = document.getElementById("proj-team");
    if (sel) sel.onchange = () => { state.team = sel.value; state.limit = 100; syncToURL(); render(); };
    const inp = document.getElementById("proj-q");
    if (inp) {
      inp.oninput = () => { state.q = inp.value; state.limit = 100; syncToURL(); renderTable(); };
    }
    renderTable();
    if (window.EEPHUS_GL) window.EEPHUS_GL.wire(banner);
  }

  function sortHead(label, key, title) {
    const active = state.sort === key;
    return `<th class="proj-sort${active ? " is-sorted" : ""}" data-psort="${key}" title="${esc(title || "Click to sort")}">${label}${active ? (state.dir < 0 ? " ▾" : " ▴") : ""}</th>`;
  }

  function renderTable() {
    const root = document.getElementById("proj-rows");
    const first = DATA.first_season;
    const list = sortRows(rows());
    const seasons = Array.from({ length: DATA.horizon }, (_, t) => first + t);
    const body = list.slice(0, state.limit).map((m, i) => {
      const cells = seasons.map((s, t) => {
        const w = warAt(m, t);
        if (w == null) {
          const milb = m.src === "prospect" && s < m.eta;
          return `<td class="proj-dim">${milb ? "MiLB" : EM_DASH}</td>`;
        }
        const lo = bandAt(m, t, "lo"), hi = bandAt(m, t, "hi");
        return `<td class="proj-war${warClass(w)}" title="${s}: mean ${fmtWar(w)} bWAR${lo != null ? ` · floor ${fmtWar(lo)} / ceiling ${fmtWar(hi)} (P10–P90)` : ""}">${fmtWar(w)}</td>`;
      }).join("");
      const tot = `${fmtWar(m.warTotal)}${m.warTotalP10 != null ? `<span class="fa-band"> (${fmtWar(m.warTotalP10)}–${fmtWar(m.warTotalP90)})</span>` : ""}`;
      const ct = m.src === "prospect"
        ? `<span class="fa-sub" title="Cost-controlled from debut - six control years (3 pre-arb + 3 arb)">control</span>`
        : (m.thru ? `${m.thru}${m.aav ? ` · ${money(m.aav)}/y` : ""}` : `<span class="fa-sub">arb/pre-arb or FA</span>`);
      const sur = m.surNpv != null
        ? `<span class="${m.surNpv >= 0 ? "proj-pos" : "proj-neg"}" title="${m.src === "prospect" ? "Platform prospect surplus value (control window, service-time aware, $/WAR-escalated)" : "NPV of (convex production value − salary) over salary-known seasons"}">${money(m.surNpv)}</span>`
        : EM_DASH;
      const link = m.src === "prospect"
        ? `<a class="fa-player-link" href="/prospx/#player=${encodeURIComponent(m.key)}"><strong>${esc(m.name)}</strong></a>`
        : `<strong>${esc(m.name)}</strong>`;
      return `<tr>
        <td>${i + 1}</td>
        <td class="proj-player">${teamLogo(m.team)}${link} <span class="fa-sub">${esc(m.pos || "")} · ${m.age != null ? Math.floor(m.age) : "?"}${m.team ? "" : " · FA"}</span> ${tagFor(m)}</td>
        ${cells}
        <td>${tot}</td>
        <td>${ct}</td>
        <td>${sur}</td>
      </tr>`;
    }).join("");
    root.innerHTML = `<table class="detail-table proj-table">
      <thead><tr><th>#</th><th>Player</th>
      ${seasons.map((s, t) => sortHead(String(s), "y" + t, `Projected ${s} bWAR (hover any cell for the floor/ceiling band)`)).join("")}
      ${sortHead(`${DATA.horizon}y <span data-gl="war">WAR</span>`, "warTotal", "Five-year projected bWAR (P10–P90 band)")}
      <th>Contract</th>
      ${sortHead("Surplus", "sur", "Veterans: production value minus salary, salary-known seasons only. Prospects: platform surplus value.")}
      </tr></thead><tbody>${body || `<tr><td colspan="${5 + seasons.length}">No players match.</td></tr>`}</tbody></table>
      ${list.length > state.limit ? `<div style="text-align:center;margin:10px 0;"><button class="chip" id="proj-more">show ${Math.min(100, list.length - state.limit)} more (${list.length - state.limit} hidden)</button></div>` : ""}`;
    root.querySelectorAll("[data-psort]").forEach(h => h.onclick = () => {
      const k = h.dataset.psort;
      if (state.sort === k) state.dir = -state.dir;
      else { state.sort = k; state.dir = -1; }
      syncToURL(); renderTable();
    });
    const more = document.getElementById("proj-more");
    if (more) more.onclick = () => { state.limit += 100; renderTable(); };
    if (window.EEPHUS_GL) window.EEPHUS_GL.wire(root);
  }

  function boot() {
    syncFromURL();
    const root = document.getElementById("proj-rows");
    if (!root) return;
    root.innerHTML = `<div class="state-message is-loading">Loading projections&hellip;</div>`;
    fetch("/data/mlb_projections.json", { cache: "no-cache" })
      .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
      .then(d => { DATA = d; render(); })
      .catch(e => {
        root.innerHTML = `<div class="state-message is-error">Projection data unavailable
          (${esc(String(e.message || e))}). Run <code>python proj_export.py</code> to regenerate
          <code>data/mlb_projections.json</code>.</div>`;
      });
    window.addEventListener("hashchange", () => { syncFromURL(); render(); });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
