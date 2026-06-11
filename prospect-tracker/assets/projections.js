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
                  dir: -1, limit: 100, player: null };
  let DETAIL = null;            // data/mlb_player_detail.json, lazy
  let DETAIL_LOADING = false;

  function syncFromURL() {
    const p = new URLSearchParams(location.hash.slice(1));
    state.player = p.get("player") || null;
    if (p.has("src")) state.src = p.get("src");
    if (p.has("pos")) state.pos = p.get("pos");
    if (p.has("team")) state.team = p.get("team");
    if (p.has("q")) state.q = p.get("q");
    if (p.has("sort")) state.sort = p.get("sort");
  }
  function syncToURL() {
    const p = new URLSearchParams();
    if (state.player) p.set("player", state.player);
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
    if (state.player) { renderPlayer(state.player); return; }
    const first = DATA.first_season;
    const teams = [...new Set((DATA.vets || []).map(m => m.team).filter(Boolean))].sort();

    banner.innerHTML = `<div class="fa-note fa-sources">
      ${DATA.n_vets} veterans (the <span data-gl="fa_projection_engine">FA projection engine</span>, league-wide)
      &middot; ${DATA.n_prospects} prospects (<span data-gl="proj_buckets">outcome buckets</span> from their PROSPX ETA)
      &middot; seasons priced at the ${first} ex-ante <span data-gl="winter_dpw">$/WAR</span> ${money(DATA.dpw_usd)},
      escalating ${(DATA.dpw_infl * 100).toFixed(0)}%/yr
      &middot; <span data-gl="contract_surplus">surplus</span> only where a real contract exists
      &middot; <button class="chip" id="proj-board-gfx" title="Download the top of this board as a PNG share card (theme-aware)">&#8681; share card</button></div>`;
    const gfxBtn = document.getElementById("proj-board-gfx");
    if (gfxBtn) gfxBtn.onclick = () => {
      if (!window.EEPHUS_HUB) return;
      const top = sortRows(rows()).slice(0, 10);
      window.EEPHUS_HUB.shareCard({
        module: "MLB Projections",
        name: "Five-Year bWAR Leaders",
        meta: `${DATA.n_vets} veterans + ${DATA.n_prospects} prospects · seasons ${DATA.first_season}-${DATA.first_season + DATA.horizon - 1}`,
        tiles: [],
        sections: [
          { title: "Top 10 · projected 5y bWAR", rows: top.slice(0, 5).map((m, i) =>
            [`${i + 1}. ${m.name}`, `${fmtWar(m.warTotal)}${m.warTotalP10 != null ? `  (${fmtWar(m.warTotalP10)}-${fmtWar(m.warTotalP90)})` : ""}`]) },
          { title: " ", rows: top.slice(5, 10).map((m, i) =>
            [`${i + 6}. ${m.name}`, `${fmtWar(m.warTotal)}${m.warTotalP10 != null ? `  (${fmtWar(m.warTotalP10)}-${fmtWar(m.warTotalP90)})` : ""}`]) },
        ],
        url: "eephus.io/projections",
        filename: "eephus-projections-board.png",
        caption: "Gate-1-validated engine · floor/mean/ceiling probability buckets · prospects join at their PROSPX ETA",
      });
    };

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
        : `<a class="fa-player-link" href="#player=${encodeURIComponent(m.key)}"><strong>${esc(m.name)}</strong></a>`;
      return `<tr>
        <td>${i + 1}</td>
        <td class="proj-player">${teamLogo(m.team)}${link} <span class="fa-sub">${esc(m.pos || "")} · ${m.age != null ? Math.floor(m.age) : "?"}${m.team ? "" : " · FA"}</span> ${tagFor(m)}<span class="proj-fa-slot" data-fa-key="${esc(m.key)}"></span></td>
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
    // Cross-module cohesion: FA-class members get a $ chip linking to
    // their market card (async via the links map; no layout shift).
    if (window.EEPHUS_HUB) {
      window.EEPHUS_HUB.links().then(L => {
        if (!L) return;
        root.querySelectorAll(".proj-fa-slot[data-fa-key]").forEach(el => {
          const row = (L.byKey || {})[el.dataset.faKey];
          if (row && row.fa) {
            el.innerHTML = ` <a class="proj-tag" href="/fa/#player=${encodeURIComponent(row.key)}" title="In the current FA class - open the market card (projected deal, verdict, comps)">$ FA</a>`;
          }
          el.removeAttribute("data-fa-key");
        });
      });
    }
    if (window.EEPHUS_GL) window.EEPHUS_GL.wire(root);
  }

  // ===========================================================================
  // MLB player page (#player={key}) - the per-player detail surface
  // (data/mlb_player_detail.json, mlb_player_export.py). Parity goal with
  // prospect detail: hero + tiles, projection fan, Savant percentile
  // sliders, pitch arsenal, season-by-season career with bWAR, FA market
  // block for class members.
  // ===========================================================================
  function headshotURL(mlbam, r) {
    return `https://img.mlbstatic.com/mlb-photos/image/upload/d_people:generic:headshot:67:current.png/w_${r || 240},q_auto:best/v1/people/${mlbam}/headshot/67/current`;
  }
  function pctClass(p) {
    return p >= 80 ? "is-elite" : p >= 60 ? "is-good" : p >= 40 ? "is-avg" : p >= 20 ? "is-low" : "is-poor";
  }
  function sliders(sc) {
    if (!sc || !sc.metrics || !sc.metrics.length) return "";
    const rows = sc.metrics.map(m => `
      <div class="mlbp-slider">
        <span class="mlbp-slider-label">${esc(m.label)}</span>
        <div class="mlbp-slider-track"><div class="mlbp-slider-fill ${pctClass(m.pct)}" style="width:${m.pct}%;"></div>
          <span class="mlbp-slider-pct ${pctClass(m.pct)}" style="left:${Math.min(94, Math.max(2, m.pct))}%;">${m.pct}</span></div>
        <span class="mlbp-slider-val">${esc(m.value)}</span>
      </div>`).join("");
    return `<div class="mlbp-section"><div class="mlbp-section-title">Statcast Percentiles <span class="fa-sub">${sc.season} · vs qualified MLB pool</span></div>${rows}</div>`;
  }
  function fanChart(p) {
    const war = (p.proj && p.proj.war) || [];
    if (war.length < 2) return "";
    const lo = (p.proj && p.proj.warP10) || [], hi = (p.proj && p.proj.warP90) || [];
    const first = DATA.first_season, W = 560, H = 170, PX = 36, PY = 16;
    const all = war.concat(lo, hi).filter(v => v != null);
    const mn = Math.min(0, ...all), mx = Math.max(1, ...all);
    const x = t => PX + t * (W - PX - 8) / (war.length - 1);
    const y = v => PY + (mx - v) * (H - PY - 24) / (mx - mn || 1);
    const pts = a => a.map((v, t) => `${x(t)},${y(v)}`).join(" ");
    const band = (lo.length && hi.length)
      ? `<polygon points="${pts(hi)} ${lo.map((v, t) => `${x(lo.length - 1 - t)},${y(lo[lo.length - 1 - t])}`).join(" ")}" class="mlbp-fan-band"/>` : "";
    const ticks = war.map((v, t) => `<text x="${x(t)}" y="${H - 6}" text-anchor="middle" class="mlbp-fan-tick">${first + t}</text>`).join("");
    const zero = (mn < 0) ? `<line x1="${PX}" x2="${W - 8}" y1="${y(0)}" y2="${y(0)}" class="mlbp-fan-zero"/>` : "";
    return `<div class="mlbp-section"><div class="mlbp-section-title">Projected bWAR <span class="fa-sub">mean + P10-P90 band · Gate-1-validated engine</span></div>
      <svg class="mlbp-fan" viewBox="0 0 ${W} ${H}" role="img" aria-label="Projected WAR path">${band}
        <polyline points="${pts(war)}" class="mlbp-fan-line"/>
        ${war.map((v, t) => `<circle cx="${x(t)}" cy="${y(v)}" r="3" class="mlbp-fan-dot"><title>${first + t}: ${fmtWar(v)}${lo[t] != null ? ` (${fmtWar(lo[t])}-${fmtWar(hi[t])})` : ""}</title></circle>`).join("")}
        ${zero}${ticks}</svg></div>`;
  }
  function arsenalTable(ar) {
    if (!ar || !ar.length) return "";
    return `<div class="mlbp-section"><div class="mlbp-section-title">Pitch Arsenal <span class="fa-sub">usage · run value /100 · whiff%</span></div>
      <table class="detail-table"><thead><tr><th>Pitch</th><th>Usage</th><th>RV/100</th><th>Whiff%</th><th>BA against</th></tr></thead>
      <tbody>${ar.map(a => `<tr><td>${esc(a.pitch || "")}</td><td>${a.usage != null ? a.usage.toFixed(1) + "%" : EM_DASH}</td>
        <td class="${a.rv100 != null && a.rv100 < 0 ? "proj-pos" : a.rv100 > 0 ? "proj-neg" : ""}">${a.rv100 != null ? a.rv100.toFixed(1) : EM_DASH}</td>
        <td>${a.whiff != null ? a.whiff.toFixed(1) + "%" : EM_DASH}</td><td>${a.ba != null ? String(a.ba) : EM_DASH}</td></tr>`).join("")}</tbody></table></div>`;
  }
  function careerTable(p) {
    const c = p.career || [];
    if (!c.length) return "";
    const head = p.isPit
      ? "<th>Year</th><th>IP</th><th>ERA</th><th>K%</th><th>BB%</th><th>bWAR</th>"
      : "<th>Year</th><th>PA</th><th>AVG/OBP/SLG</th><th>OPS</th><th>HR</th><th>SB</th><th>BB%</th><th>K%</th><th>ISO</th><th>bWAR</th>";
    const rows = c.slice().reverse().map(r => p.isPit
      ? `<tr><td>${r.y}</td><td>${r.ip ?? EM_DASH}</td><td>${r.era != null ? r.era.toFixed(2) : EM_DASH}</td><td>${r.kPct != null ? r.kPct + "%" : EM_DASH}</td><td>${r.bbPct != null ? r.bbPct + "%" : EM_DASH}</td><td>${r.war != null ? r.war.toFixed(1) : EM_DASH}</td></tr>`
      : `<tr><td>${r.y}</td><td>${r.pa ?? EM_DASH}</td><td>${esc(r.avg || "-")}/${esc(r.obp || "-")}/${esc(r.slg || "-")}</td><td>${esc(r.ops || EM_DASH)}</td><td>${r.hr ?? EM_DASH}</td><td>${r.sb ?? EM_DASH}</td><td>${r.bbPct != null ? r.bbPct + "%" : EM_DASH}</td><td>${r.kPct != null ? r.kPct + "%" : EM_DASH}</td><td>${r.iso != null ? String(r.iso).replace(/^0(?=\.)/, "") : EM_DASH}</td><td>${r.war != null ? r.war.toFixed(1) : EM_DASH}</td></tr>`).join("");
    return `<div class="mlbp-section"><div class="mlbp-section-title">Career <span class="fa-sub">MLB seasons · bWAR (Baseball-Reference)</span></div>
      <table class="detail-table"><thead><tr>${head}</tr></thead><tbody>${rows}</tbody></table></div>`;
  }
  function faBlock(p) {
    const f = p.fa;
    if (!f) return "";
    const verd = f.verdict ? `<span class="mlbp-tile-chip">${esc(f.verdict)}</span>` : "";
    const cells = [
      ["Projected", f.projYears != null ? `${f.projYears}y / ${money(f.projGuar)}` : EM_DASH],
      ["Proj AAV", f.projAav != null ? `${money(f.projAav)}${f.projAavP10 != null ? ` <span class="fa-band">(${money(f.projAavP10)}-${money(f.projAavP90)})</span>` : ""}` : EM_DASH],
      ["Rational value", f.rational != null ? money(f.rational) : EM_DASH],
      ["Contract surplus", f.surplus != null ? money(f.surplus) : EM_DASH],
      ["Deal+", f.dealPlus != null ? String(Math.round(f.dealPlus)) : EM_DASH],
      ["Prior AAV", f.prevAav != null ? money(f.prevAav) : EM_DASH],
    ];
    return `<div class="mlbp-section"><div class="mlbp-section-title">Free Agency <span class="fa-sub">${esc(f.status || "")} · gate-validated market model</span> ${verd}</div>
      <div class="mlbp-grid">${cells.map(([l, v]) => `<div class="mlbp-cell"><span class="mlbp-cell-label">${l}</span><span class="mlbp-cell-val">${v}</span></div>`).join("")}</div>
      <div class="fa-sub" style="margin-top:6px;"><a class="fa-player-link" href="/fa/#player=${encodeURIComponent(p.key)}">market card on the class board →</a></div></div>`;
  }
  function renderPlayer(key) {
    const root = document.getElementById("proj-rows");
    const bar = document.getElementById("proj-filters");
    const banner = document.getElementById("proj-banner");
    if (banner) banner.innerHTML = "";
    if (bar) bar.innerHTML = `<a class="chip" href="#" id="mlbp-back">← back to projections</a>`;
    const back = document.getElementById("mlbp-back");
    if (back) back.onclick = (e) => { e.preventDefault(); state.player = null; syncToURL(); render(); };
    if (!DETAIL) {
      root.innerHTML = `<div class="state-message is-loading">Loading player&hellip;</div>`;
      if (!DETAIL_LOADING) {
        DETAIL_LOADING = true;
        fetch("/data/mlb_player_detail.json", { cache: "no-cache" })
          .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
          .then(d => { DETAIL = d; if (state.player) renderPlayer(state.player); })
          .catch(e => { root.innerHTML = `<div class="state-message is-error">Player detail unavailable (${esc(String(e.message || e))}). Run <code>python mlb_player_export.py</code>.</div>`; });
      }
      return;
    }
    const p = (DETAIL.players || {})[key];
    if (!p) {
      root.innerHTML = `<div class="state-message">No detail for "${esc(key)}". <a href="#" onclick="location.hash='';return false;">Back</a>.</div>`;
      return;
    }
    const photo = p.mlbam
      ? `<img class="mlbp-headshot" src="${headshotURL(p.mlbam, 240)}" alt="" onerror="this.style.visibility='hidden'">` : "";
    const tiles = [];
    const tile = (label, val, cls) => tiles.push(`<div class="mlbp-tile"><span class="mlbp-tile-label">${label}</span><span class="mlbp-tile-val ${cls || ""}">${val}</span></div>`);
    if (p.proj && p.proj.warTotal != null)
      tile(`${(p.proj.war || []).length}y WAR`, `${fmtWar(p.proj.warTotal)}${p.proj.warTotalP10 != null ? `<span class="fa-band"> (${fmtWar(p.proj.warTotalP10)}-${fmtWar(p.proj.warTotalP90)})</span>` : ""}`);
    if (p.proj && p.proj.surNpv != null) tile("Surplus NPV", money(p.proj.surNpv), p.proj.surNpv >= 0 ? "proj-pos" : "proj-neg");
    if (p.swingPlus != null) tile("Swing+", `${p.swingPlus}<span class="fa-band"> n=${p.swingN}</span>`, p.swingPlus >= 105 ? "proj-pos" : p.swingPlus <= 95 ? "proj-neg" : "");
    if (p.fa && p.fa.projAav != null) tile("Proj AAV", money(p.fa.projAav));
    const contract = p.proj && p.proj.thru
      ? `signed thru ${p.proj.thru}${p.proj.aav ? ` · ${money(p.proj.aav)}/y` : ""}`
      : (p.fa ? `free agent${p.fa.type ? ` · ${esc(p.fa.type)}` : ""}` : "arb / pre-arb");
    // Prospect origin line (ex-PROSPX players): the FV arc endpoints +
    // debut date - the hub strip carries the link to the full arc.
    const org = p.origin;
    const originLine = (org && org.prospx)
      ? `<div class="fa-sub" style="margin-top:4px;">ex-PROSPX prospect${org.fvOpen != null && org.fvClose != null ? ` · FV ${org.fvOpen} → ${org.fvClose}` : ""}${org.debut ? ` · debuted ${esc(org.debut)}` : ""}</div>`
      : "";
    root.innerHTML = `<div class="mlbp-page">
      <div id="mlbp-hub"></div>
      <div class="mlbp-hero">
        ${photo}
        <div class="mlbp-hero-main">
          <div class="mlbp-name">${teamLogo(p.team)}<h2>${esc(p.name || key)}</h2></div>
          <div class="fa-sub">${esc(p.pos || "")}${p.age != null ? ` · age ${Math.floor(p.age)}` : ""}${p.team ? ` · ${esc(p.team)}` : " · FA"} · ${contract}</div>
          ${originLine}
          <div style="margin-top:8px;"><button class="chip" id="mlbp-gfx" title="Download this player page as a PNG share card (theme-aware)">&#8681; share card</button></div>
        </div>
        <div class="mlbp-tiles">${tiles.join("")}</div>
      </div>
      ${fanChart(p)}
      ${p.twoWay && p.proj && p.proj.warHit ? `<div class="fa-note">Two-way projection: the path above SUMS both sides per season - hitting ${p.proj.warHit.map(fmtWar).join(" / ")} + pitching ${p.proj.warPit.map(fmtWar).join(" / ")}.</div>` : ""}
      ${p.twoWay ? `<div class="mlbp-section-title" style="margin-top:18px;">As a hitter</div>` : ""}
      ${sliders(p.sc)}
      ${(p.isPit && !p.twoWay) ? arsenalTable(p.arsenal) : ""}
      ${p.twoWay ? `<div class="mlbp-section-title" style="margin-top:18px;">As a pitcher</div>${sliders(p.scPit)}${arsenalTable(p.arsenal)}` : ""}
      ${faBlock(p)}
      ${careerTable(p)}
      ${p.twoWay && p.careerPit && p.careerPit.length ? careerTable({ ...p, career: p.careerPit, isPit: true }) : ""}
      <div class="fa-note" style="margin-top:14px;">Projections: the FA module's Gate-1-validated engine (bands = empirical residual quantiles). Statcast percentiles vs the season's qualified MLB pool. ${p.swingPlus != null ? "Swing+ by Will Cahoon (MLB bat tracking 2024+)." : ""}</div>
    </div>`;
    // hub strip (cross-module identity) - lazy, never blocks the paint
    if (window.EEPHUS_HUB) {
      window.EEPHUS_HUB.links().then(L => {
        const row = L && (L.byKey || {})[key];
        const el = document.getElementById("mlbp-hub");
        if (el && row) el.innerHTML = window.EEPHUS_HUB.stripHTML(row, "mlb");
      });
      const btn = document.getElementById("mlbp-gfx");
      if (btn) btn.onclick = () => shareMlbCard(p);
    }
  }

  // Unified share card (EEPHUS_HUB canvas template) - the MLB module's
  // data priorities: projection band + surplus + Swing+ up top, Statcast
  // percentiles and (pitchers) arsenal as the body sections.
  function shareMlbCard(p) {
    const first = DATA.first_season;
    const tiles = [];
    if (p.proj && p.proj.warTotal != null)
      tiles.push({ label: `${(p.proj.war || []).length}y WAR`, value: fmtWar(p.proj.warTotal) });
    if (p.proj && p.proj.surNpv != null)
      tiles.push({ label: "Surplus", value: money(p.proj.surNpv),
                   color: p.proj.surNpv >= 0 ? undefined : "#FF6B6B" });
    if (p.swingPlus != null)
      tiles.push({ label: "Swing+", value: String(Math.round(p.swingPlus)) });
    if (p.fa && p.fa.projAav != null)
      tiles.push({ label: "proj AAV", value: money(p.fa.projAav) });
    const sections = [];
    if (p.proj && (p.proj.war || []).length) {
      sections.push({ title: `Projected bWAR ${first}-${first + (p.proj.war.length - 1)}`,
        rows: p.proj.war.map((w, t) => [String(first + t),
          `${fmtWar(w)}${(p.proj.warP10 || [])[t] != null ? `  (${fmtWar(p.proj.warP10[t])}-${fmtWar(p.proj.warP90[t])})` : ""}`]) });
    }
    if (p.isPit && p.arsenal && p.arsenal.length) {
      sections.push({ title: "Pitch arsenal · usage / whiff",
        rows: p.arsenal.slice(0, 6).map(a => [a.pitch || "?",
          `${a.usage != null ? a.usage.toFixed(0) + "%" : "-"} / ${a.whiff != null ? a.whiff.toFixed(0) + "%" : "-"}`]) });
    } else if (p.sc && p.sc.metrics && p.sc.metrics.length) {
      sections.push({ title: `Statcast percentiles · ${p.sc.season}`,
        rows: p.sc.metrics.map(m => [m.label, `${m.value}  (${m.pct})`]) });
    }
    window.EEPHUS_HUB.shareCard({
      module: "MLB Projections",
      name: p.name || p.key,
      meta: `${p.pos || ""}${p.age != null ? ` · age ${Math.floor(p.age)}` : ""}${p.team ? ` · ${p.team}` : " · FA"}`,
      sub: p.fa && p.fa.verdict ? `FA verdict: ${String(p.fa.verdict).toUpperCase()}` : "",
      headshotURL: p.mlbam ? headshotURL(p.mlbam, 240) : null,
      tiles, sections,
      url: `eephus.io/projections/#player=${p.key}`,
      filename: `eephus-${p.key}-mlb-card.png`,
      caption: "Gate-1-validated projection engine · bands = P10-P90 · Statcast percentiles vs qualified MLB pool",
    });
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
