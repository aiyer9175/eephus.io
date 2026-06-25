// Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) / Anirudh Iyer - All Rights Reserved
// Proprietary and confidential.
//
// Trade Machine - relocated to live under MLB Projections (originally a PROSPX
// module by Anirudh Iyer). The board + evaluator logic below is the exact PROSPX
// implementation; this header supplies the handful of app globals that code reads
// so it runs standalone on the /projections/ page. Data is sourced from standalone
// files: data/trade_values.json (board + prospect surplus) and
// data/mlb_player_detail.json (MLB contract surplus) - no live PROSPX state needed.
(function () {
  "use strict";

  const DATA_BASE = "/data/";
  let _dataVersion = "";

  // Stand-ins for the PROSPX app globals the extracted code expects.
  const state = { pages: {}, pageSizes: {}, section: "trademachine" };
  // Evaluator prospect search/seed pool, filled from trade_values.json prospects.
  const DATA = { players: [] };

  // In PROSPX, clicking a board player opens an in-app detail; here we deep-link
  // back to that prospect's PROSPX page.
  function renderPlayerDetail(key) {
    if (key) location.href = "/prospx/#player=" + encodeURIComponent(key);
  }
// Pagination window helper (transitive dep of renderPaginationStrip), from PROSPX.
function computePageWindow(cur, total) {
  if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1);
  const out = [1];
  const lo = Math.max(2, cur - 1);
  const hi = Math.min(total - 1, cur + 1);
  if (lo > 2) out.push("…");
  for (let i = lo; i <= hi; i++) out.push(i);
  if (hi < total - 1) out.push("…");
  out.push(total);
  return out;
}

function pageSlice(arr, page, pageSize) {
  const p = Math.max(1, page | 0);
  return arr.slice((p - 1) * pageSize, p * pageSize);
}

function renderPaginationStrip(currentPage, totalItems, pageSize, dataKey) {
  const total = Math.ceil(totalItems / Math.max(1, pageSize));
  if (total <= 1) return "";
  const cur = Math.min(Math.max(1, currentPage), total);
  const pages = computePageWindow(cur, total);
  const chips = pages.map(p =>
    p === "…"
      ? `<span class="pg-ellipsis">…</span>`
      : `<button class="pg-chip${p === cur ? " active" : ""}" data-${dataKey}-page="${p}" type="button">${p}</button>`
  ).join("");
  const lo = (cur - 1) * pageSize + 1;
  const hi = Math.min(cur * pageSize, totalItems);
  return `
    <div class="pg-strip">
      <button class="pg-nav" data-${dataKey}-page="${Math.max(1, cur - 1)}" type="button"${cur === 1 ? " disabled" : ""}>◀ Prev</button>
      ${chips}
      <button class="pg-nav" data-${dataKey}-page="${Math.min(total, cur + 1)}" type="button"${cur === total ? " disabled" : ""}>Next ▶</button>
      <span class="pg-count">Showing ${lo}–${hi} of ${totalItems}</span>
    </div>`;
}

function escapeHtml(s) {
  if (s == null) return "";
  return String(s).replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  }[c]));
}
// ORG abbreviation -> ESPN logo slug (same map as projections.js / build_site / prospx).
const _TM_ESPN_SLUGS = {
  ARI: "ari", ATH: "ath", ATL: "atl", BAL: "bal", BOS: "bos",
  CHC: "chc", CHW: "chw", CIN: "cin", CLE: "cle", COL: "col",
  DET: "det", HOU: "hou", KCR: "kc", LAA: "laa", LAD: "lad",
  MIA: "mia", MIL: "mil", MIN: "min", NYM: "nym", NYY: "nyy",
  PHI: "phi", PIT: "pit", SDP: "sd", SEA: "sea", SFG: "sf",
  STL: "stl", TBR: "tb", TEX: "tex", TOR: "tor", WSN: "wsh",
};
function _tmTeamLogo(org) {
  if (!org) return "";
  const slug = _TM_ESPN_SLUGS[org] || String(org).toLowerCase();
  return `<img class="tm-logo" src="https://a.espncdn.com/i/teamlogos/mlb/500/${slug}.png" `
       + `alt="${escapeHtml(org)}" loading="lazy" onerror="this.style.display='none'">`;
}
// Surplus-$ magnitude -> tier color (evaluator; mirrors the board's _TB_TIER_COLORS feel).
function _tmValColor(mm) {
  const v = Math.abs(mm || 0);
  if (mm < 0) return "var(--down, #e05c5c)";
  if (v >= 80) return "var(--card-gold)";
  if (v >= 35) return "var(--neon-green)";
  if (v >= 12) return "var(--neon-cyan, var(--accent-cyan))";
  return "var(--text-secondary)";
}
const _TM = { a: [], b: [], detail: null, detailLoading: false };

function _tmEnsureDetail() {
  if (_TM.detail || _TM.detailLoading) return;
  _TM.detailLoading = true;
  fetch("/data/mlb_player_detail.json", { cache: "no-cache" })
    .then(r => (r.ok ? r.json() : null))
    .then(j => { _TM.detail = (j && j.players) || {};
      if (state.section === "trademachine" || state.section === "tradeboard") renderTradeMachine(); })
    .catch(() => { _TM.detail = {}; });
}

// Translatability with MLB Projections: a "⇄ Trade Machine" link on a player's
// /projections/ page deep-links here as #tab=trademachine&tm=<kind>:<key>, which
// pre-loads that player into Side A so you can value him against a package.
function _tmSeedFromURL() {
  if (_TM.seeded) return;
  const seed = new URLSearchParams((location.hash || "").replace(/^#/, "")).get("tm");
  if (!seed) { _TM.seeded = true; return; }
  const ci = seed.indexOf(":");
  const kind = seed.slice(0, ci), key = seed.slice(ci + 1);
  if (kind === "prospect") {
    const p = (DATA.players || []).find(x => x.player_key === key);
    const sv = p && p.surplus && p.surplus.value_mm;
    if (sv != null) { _TM.a.push({ kind: "prospect", key, name: p.player_name,
      sub: `${p.position || ""} · ${p.org || ""} · FV ${p.fv_close ?? "?"}`, mm: sv }); _TM.seeded = true; }
  } else if (kind === "mlb") {
    if (!_TM.detail) return;                 // detail still loading; seed on the re-render
    const d = _TM.detail[key];
    if (d && d.proj && d.proj.surNpv != null) _TM.a.push({ kind: "mlb", key, name: d.name,
      sub: `${d.pos || ""} · ${d.team || "FA"} · contract surplus`, mm: d.proj.surNpv / 1e6 });
    _TM.seeded = true;
  } else { _TM.seeded = true; }
}

function _tmSearch(q) {
  q = q.trim().toLowerCase();
  if (q.length < 2) return [];
  const out = [];
  for (const p of (DATA.players || [])) {
    if (out.length >= 6) break;
    if ((p.player_name || "").toLowerCase().includes(q)) {
      const sv = p.surplus && p.surplus.value_mm;
      if (sv != null) out.push({ kind: "prospect", key: p.player_key,
        name: p.player_name, org: p.org || "", pos: p.position || "",
        sub: `${p.position || ""} · ${p.org || ""} · FV ${p.fv_close ?? "?"}`,
        mm: sv });
    }
  }
  if (_TM.detail) {
    for (const k in _TM.detail) {
      if (out.length >= 10) break;
      const d = _TM.detail[k];
      if ((d.name || "").toLowerCase().includes(q) && d.proj && d.proj.surNpv != null) {
        out.push({ kind: "mlb", key: k, name: d.name,
          org: d.team || "", pos: d.pos || "",
          sub: `${d.pos || ""} · ${d.team || "FA"} · contract surplus`,
          mm: d.proj.surNpv / 1e6 });
      }
    }
  }
  return out;
}

function _tmTotal(side) {
  return side.reduce((s, x) => s + (x.mm || 0), 0);
}

// One shared dead-band for "even" trade verdicts, used by BOTH the Trade
// Machine and the Transactions Trade Audit so the two never disagree on what
// counts as balanced. The wider $5M band is deliberate: surplus dollars carry
// real model uncertainty, so a sub-$5M edge is not a meaningful "winner."
const BALANCED_THRESHOLD_MM = 5;

function renderTradeMachine() {
  const el = document.getElementById("trade-machine");
  if (!el) return;
  _tmEnsureDetail();
  _tmSeedFromURL();
  const sideHtml = (side, label) => {
    const list = _TM[side].map((x, i) => `
      <div class="tm-row">
        <span class="tm-kind tm-kind--${x.kind}" title="${x.kind === "prospect" ? "Prospect (xFV surplus)" : "MLB (contract surplus)"}">${x.kind === "prospect" ? "P" : "M"}</span>
        ${_tmTeamLogo(x.org)}
        <a class="fa-player-link tm-name" href="${x.kind === "prospect" ? `/prospx/#player=${encodeURIComponent(x.key)}` : `/projections/#player=${encodeURIComponent(x.key)}`}">${escapeHtml(x.name)}</a>
        <span class="tm-sub">${escapeHtml(x.pos || "")}</span>
        <span class="tm-val" style="color:${_tmValColor(x.mm)};">${x.mm >= 0 ? "$" : "-$"}${Math.abs(x.mm).toFixed(1)}M</span>
        <button class="tm-x" data-tm-remove="${side}:${i}" title="Remove">×</button>
      </div>`).join("");
    const tot = _tmTotal(_TM[side]);
    return `<div class="tm-side">
      <div class="tm-side-head"><span>${label} receives</span> <span class="tm-total" style="color:${_tmValColor(tot)};">$${tot.toFixed(1)}M</span></div>
      <input class="tm-search" type="search" placeholder="Add player (prospect or MLB)…" data-tm-search="${side}" autocomplete="off">
      <div class="tm-results" data-tm-results="${side}"></div>
      ${list || '<div class="tm-empty">no players yet</div>'}
    </div>`;
  };
  const dA = _tmTotal(_TM.a), dB = _tmTotal(_TM.b);
  const have = _TM.a.length || _TM.b.length;
  const sum = Math.max(1e-6, Math.max(0, dA) + Math.max(0, dB));
  const aPct = Math.round(100 * Math.max(0, dA) / sum);
  const diff = Math.abs(dA - dB);
  const bal = diff < BALANCED_THRESHOLD_MM;
  const lead = dA > dB ? "A" : "B";
  const verdict = have
    ? `<div class="tm-verdict">
         <div class="tm-balbar" title="value split A vs B">
           <div class="tm-balbar-a" style="width:${aPct}%"></div>
           <div class="tm-balbar-b" style="width:${100 - aPct}%"></div>
         </div>
         <div class="tm-balrow">
           <span class="tm-balverdict${bal ? " is-bal" : ""}">${bal ? "≈ balanced package" : `Side ${lead} receives +$${diff.toFixed(1)}M of value`}</span>
           <span class="fa-sub">one currency: prospect surplus (control-window NPV) + MLB contract surplus</span>
         </div>
       </div>`
    : "";
  el.innerHTML = `<div class="tm-wrap">
    <div class="detail-title" style="font-size:13px;">Trade Machine
      <span class="detail-title-sub">value both sides of a deal in the platform's surplus currency</span>
    </div>
    <div class="tm-grid">${sideHtml("a", "Side A")}${sideHtml("b", "Side B")}</div>
    ${verdict}
  </div>`;
  el.querySelectorAll("[data-tm-search]").forEach(inp => {
    inp.oninput = () => {
      const side = inp.dataset.tmSearch;
      const res = el.querySelector(`[data-tm-results="${side}"]`);
      const hits = _tmSearch(inp.value);
      res.innerHTML = hits.map((h, i) =>
        `<button class="tm-hit" data-tm-add="${side}:${i}" type="button">
           <strong>${escapeHtml(h.name)}</strong> <span class="tm-sub">${escapeHtml(h.sub)}</span>
           <span class="tm-val">$${h.mm.toFixed(1)}M</span></button>`).join("");
      res._hits = hits;
    };
  });
  el.querySelectorAll("[data-tm-results]").forEach(res => {
    res.onclick = (e) => {
      const b = e.target.closest("[data-tm-add]");
      if (!b || !res._hits) return;
      const [side, i] = b.dataset.tmAdd.split(":");
      _TM[side].push(res._hits[Number(i)]);
      renderTradeMachine();
    };
  });
  el.querySelectorAll("[data-tm-remove]").forEach(b => {
    b.onclick = () => {
      const [side, i] = b.dataset.tmRemove.split(":");
      _TM[side].splice(Number(i), 1);
      renderTradeMachine();
    };
  });
}

// ─── Trade Board ──────────────────────────────────────────────────────────────
let _tbData   = null;   // also exposed as window._tbData for renderPlayerDetail fallback
let _tbPool   = "all";
let _tbTier   = "all";
let _tbPos    = "all";
let _tbOrg    = "all";
let _tbExactPos = "all";
let _tbSort   = "trade_desc";
let _tbQ      = "";        // free-text search

// Mock trade state: two sides, each an array of player objects from _tbData
const _mockTrade = { a: [], b: [] };

const _TB_POS_BUCKETS = {
  C:  p => _tbPrimaryPos(p) === "C",
  "1B": p => _tbPrimaryPos(p) === "1B",
  "2B": p => _tbPrimaryPos(p) === "2B",
  SS: p => _tbPrimaryPos(p) === "SS",
  "3B": p => _tbPrimaryPos(p) === "3B",
  LF: p => _tbPrimaryPos(p) === "LF",
  CF: p => _tbPrimaryPos(p) === "CF",
  RF: p => _tbPrimaryPos(p) === "RF",
  SP: p => ["SP", "RHP", "LHP", "P"].includes(_tbPrimaryPos(p)),
  RP: p => ["RP", "CL", "SIRP", "MIRP"].includes(_tbPrimaryPos(p)),
};
const _TB_TIER_COLORS = {
  elite:"var(--card-gold)", high:"var(--neon-green)",
  mid:"var(--neon-cyan, var(--accent-cyan))", low:"var(--text-secondary)", minimal:"var(--text-tertiary)",
};
function _tbIsMlb(p) {
  return p && (p.status === "graduated" || p.status === "debuted");
}
function _tbPrimaryPos(pos) {
  const s = String(pos || "").toUpperCase().trim();
  if (!s) return "";
  const parts = s.split("/").map(x => x.trim()).filter(Boolean);
  const order = ["C","SS","CF","2B","3B","1B","LF","RF","OF","SP","RP","CL","RHP","LHP","P","DH"];
  return order.find(x => parts.includes(x)) || parts[0] || "";
}
function _tbSortRows(rows) {
  const num = v => Number.isFinite(Number(v)) ? Number(v) : null;
  const cmpText = (a, b) => String(a || "").localeCompare(String(b || ""));
  const withTradeTiebreak = (cmp, a, b) => cmp || ((num(b.trade_value_mm) ?? -1) - (num(a.trade_value_mm) ?? -1));
  rows.sort((a, b) => {
    if (_tbSort === "age_asc") return withTradeTiebreak((num(a.age) ?? 999) - (num(b.age) ?? 999), a, b);
    if (_tbSort === "age_desc") return withTradeTiebreak((num(b.age) ?? -1) - (num(a.age) ?? -1), a, b);
    if (_tbSort === "fv_desc") return withTradeTiebreak((num(b.fv) ?? -1) - (num(a.fv) ?? -1), a, b);
    if (_tbSort === "org_asc") return withTradeTiebreak(cmpText(a.org, b.org), a, b);
    if (_tbSort === "pos_asc") return withTradeTiebreak(cmpText(_tbPrimaryPos(a.position), _tbPrimaryPos(b.position)), a, b);
    return (num(b.trade_value_mm) ?? -1) - (num(a.trade_value_mm) ?? -1);
  });
  return rows;
}
function _tbPopulateSelectFilters() {
  if (!_tbData) return;
  const players = _tbData.players || [];
  const orgSel = document.getElementById("tb-org-filter");
  const posSel = document.getElementById("tb-exact-pos-filter");
  if (orgSel && orgSel.options.length <= 1) {
    const orgs = Array.from(new Set(players.map(p => p.org).filter(Boolean))).sort();
    orgSel.innerHTML = `<option value="all">All orgs</option>` + orgs.map(o => `<option value="${escapeHtml(o)}">${escapeHtml(o)}</option>`).join("");
    orgSel.value = _tbOrg;
  }
  if (posSel && posSel.options.length <= 1) {
    const pos = Array.from(new Set(players.map(p => _tbPrimaryPos(p.position)).filter(Boolean))).sort();
    posSel.innerHTML = `<option value="all">All positions</option>` + pos.map(p => `<option value="${escapeHtml(p)}">${escapeHtml(p)}</option>`).join("");
    posSel.value = _tbExactPos;
  }
}

function _tbWorryBadge(w) {
  if (!w || w.score < 0.15) return "";
  const label = w.type === "approach" ? "approach" : w.type === "contact_quality" ? "contact" : "skills";
  const col = w.score > 0.5 ? "var(--neon-red)" : "var(--neon-amber)";
  return `<span style="font-size:10px;color:${col}" title="Worriedness ${(w.score*100).toFixed(0)}% - ${label} signal">⚠ ${label}</span>`;
}
function _tbCtrlBadge(p) {
  const ctrl   = p.remaining_control_years;
  const cc     = p.contract || {};
  const isMlb  = p.status === "graduated" || p.status === "debuted";

  if (!isMlb) {
    // Active MiLB prospect - only show something if they have a real MLB deal
    const hasDeal = cc.signed_through || (cc.aav_mm && cc.aav_mm > 0.5);
    if (!hasDeal) return "";  // No MLB deal yet; nothing to show
    const fa  = cc.fa_year ? `FA ${cc.fa_year}` : (cc.signed_through ? `thru ${cc.signed_through}` : "");
    const sal = cc.current_salary_mm
      ? `$${cc.current_salary_mm < 1 ? (cc.current_salary_mm*1000).toFixed(0)+"k" : cc.current_salary_mm.toFixed(1)+"M"}`
      : null;
    return `<span style="font-size:10px;color:var(--neon-amber);">${escapeHtml([sal, fa].filter(Boolean).join(" · "))}</span>`;
  }

  // MLB player: full contract spec
  const phase = cc.phase || " - ";
  const sal   = cc.current_salary_mm != null
    ? (cc.current_salary_mm < 1 ? `$${(cc.current_salary_mm*1000).toFixed(0)}k` : `$${cc.current_salary_mm.toFixed(1)}M`)
    : null;
  const fa    = cc.fa_year ? `FA ${cc.fa_year}` : null;
  // Contract structural options (player opt-outs / club options)
  // Format year ranges compactly: [2030,2031,2032,2033] → "2030-33"
  function _fmtYears(yrs) {
    if (!yrs || !yrs.length) return null;
    if (yrs.length === 1) return String(yrs[0]);
    const lo = yrs[0], hi = yrs[yrs.length - 1];
    return lo === hi ? String(lo) : `${lo}-${String(hi).slice(-2)}`;
  }
  const pOpts = cc.player_opt_years && cc.player_opt_years.length
    ? `P-opt ${_fmtYears(cc.player_opt_years)}` : null;
  const cOpts = cc.club_opt_years && cc.club_opt_years.length
    ? `C-opt ${_fmtYears(cc.club_opt_years)}` : null;

  const tip = [sal && `Salary: ${sal}/yr`, pOpts, cOpts].filter(Boolean).join(" · ");
  const col = ctrl >= 5 ? "var(--neon-green)" : ctrl >= 2 ? "var(--neon-amber)" : "var(--text-secondary)";
  const parts = [
    `<span style="font-weight:600;">${escapeHtml(phase)}</span>`,
    sal  ? `<span style="color:${col}">${sal}</span>` : "",
    pOpts ? `<span style="color:var(--neon-amber);font-size:9px;" title="Player can opt out">${escapeHtml(pOpts)}</span>` : "",
    cOpts ? `<span style="color:var(--text-secondary);font-size:9px;" title="Team holds option">${escapeHtml(cOpts)}</span>` : "",
  ].filter(Boolean).join(" · ");

  return `<span style="font-size:10px;line-height:1.3;" title="${escapeHtml(tip)}">${parts}</span>`;
}
function _tbFmt(mm) {
  if (mm == null) return " - ";
  return mm >= 100 ? `$${Number(mm).toFixed(0)}M` : `$${Number(mm).toFixed(1)}M`;
}

// ── Leaderboard render ──────────────────────────────────────────────────────
function _renderTBRows() {
  const wrap = document.getElementById("tradeboard-content");
  if (!wrap || !_tbData) return;
  const q = _tbQ.toLowerCase().trim();

  let rows = (_tbData.players || []).filter(p => {
    if (!p || p.trade_value_mm == null) return false;
    if (_tbPool === "mlb" && !_tbIsMlb(p)) return false;
    if (_tbPool === "milb" && _tbIsMlb(p)) return false;
    if (_tbTier !== "all" && p.trade_value_tier !== _tbTier) return false;
    if (_tbPos  !== "all") {
      const fn = _TB_POS_BUCKETS[_tbPos];
      if (fn && !fn(p.position || "")) return false;
    }
    if (_tbOrg !== "all" && String(p.org || "") !== _tbOrg) return false;
    if (_tbExactPos !== "all" && _tbPrimaryPos(p.position) !== _tbExactPos) return false;
    if (q && !(p.player_name || "").toLowerCase().includes(q)) return false;
    return true;
  });
  rows = _tbSortRows(rows);

  if (!rows.length) {
    wrap.innerHTML = '<div class="empty-state">No players match.</div>';
    return;
  }

  if (!state.pages) state.pages = {};
  const pageSize = state.pageSizes && state.pageSizes.tradeboard ? state.pageSizes.tradeboard : 100;
  const totalPages = Math.max(1, Math.ceil(rows.length / pageSize));
  if ((state.pages.tradeboard || 1) > totalPages) state.pages.tradeboard = 1;
  const curPage = state.pages.tradeboard || 1;
  const pagedRows = pageSlice(rows, curPage, pageSize);
  const topPager = renderPaginationStrip(curPage, rows.length, pageSize, "tradeboard");

  let html = `<div style="margin:6px 0 4px;color:var(--text-secondary);font-size:11px;">${rows.length} players · ${escapeHtml(_tbData.generated_at || "")}</div>
  ${topPager}
  <table class="stats-table" style="width:100%;border-collapse:collapse;">
  <thead><tr style="font-size:11px;color:var(--text-secondary);">
    <th style="padding:5px 3px 3px;">#</th>
    <th style="padding:5px 3px 3px;">Player</th>
    <th style="padding:5px 3px 3px;text-align:right;" title="Current age (decimal years)">Age</th>
    <th style="padding:5px 3px 3px;">Pos</th>
    <th style="padding:5px 3px 3px;">Org</th>
    <th style="padding:5px 3px 3px;text-align:right;" title="Future Value grade (prospects only - hidden for MLB players where FV is no longer relevant)">FV</th>
    <th style="padding:5px 3px 3px;text-align:right;" title="Trade value point estimate">Trade $</th>
    <th style="padding:5px 3px 3px;" title="Contract: phase · salary · free agency year (MLB) or remaining controlled seasons (MiLB)">Contract</th>
    <th style="padding:5px 3px 3px;">Signals</th>
  </tr></thead><tbody>`;

  pagedRows.forEach((p, i) => {
    const rank = (curPage - 1) * pageSize + i + 1;
    const tv    = p.trade_value_mm;
    const tier  = p.trade_value_tier || "low";
    const tvCol = _TB_TIER_COLORS[tier] || "var(--text-secondary)";
    // FV only meaningful for active MiLB prospects - hide for MLB players
    const isProspect = p.status === "active";
    const fv    = isProspect && p.fv != null ? Number(p.fv).toFixed(0) : "";
    // Position: trade_values.json now carries fielding-corrected position
    const pos   = escapeHtml(p.position || "");
    const org   = escapeHtml(p.org || "");   // may be empty for some players
    const name  = escapeHtml(p.player_name || "?");
    const isMlb = _tbIsMlb(p);
    const statusCol = isMlb ? "var(--neon-violet)" : "var(--neon-green)";
    const statusLbl = isMlb ? "MLB" : "MiLB";
    const lo = p.trade_value_lo, hi = p.trade_value_hi;
    const rangeTip = (lo != null && hi != null) ? `Range: $${lo}–$${hi}M` : "";
    const flash = p.flash || {};
    const injD  = p.injury_discount || 0;

    // Navigate to player detail using goToPlayer (correct path for both
    // MiLB and graduated players). If no key, no navigation.
    const rowClick = p.player_key
      ? `onclick="event.preventDefault();goToPlayer('${escapeHtml(p.player_key)}');" style="cursor:pointer;"`
      : "";

    // Signals: status badge + ceiling flag + injury warning + GRPO breakout badge.
    let signals = `<span style="color:${statusCol};font-size:10px;">${statusLbl}</span>`;
    if (flash.is_bimodal) signals += ` <span style="color:var(--card-gold);font-size:10px;" title="Ceiling player (p_click=${flash.p_click})">↑</span>`;
    if (injD > 0.05)      signals += ` <span style="color:var(--neon-red);font-size:10px;" title="Injury discount ${(injD*100).toFixed(0)}%">⚕</span>`;
    // GRPO breakout badge - shows group comps panel on click
    const grpoSc = p.grpo_breakout_score;
    const grpoAdj = p.grpo_fv_adj;
    if (grpoSc != null) {
      const grpoCol = grpoSc >= 0.70 ? "var(--neon-green)" : grpoSc >= 0.50 ? "var(--neon-amber)" : "var(--text-secondary)";
      const adjStr  = grpoAdj != null && Math.abs(grpoAdj) >= 0.5 ? ` ${grpoAdj > 0 ? "+" : ""}${grpoAdj.toFixed(1)}FV` : "";
      signals += ` <button class="chip" style="padding:1px 5px;font-size:9px;color:${grpoCol};border-color:${grpoCol};"
        onclick="event.stopPropagation();_tbShowGroup('${escapeHtml(p.player_key||'')}');"
        title="GRPO breakout score ${(grpoSc*100).toFixed(0)}%${adjStr ? ' · FV adj'+adjStr : ''} - click to see profile group">
        G${(grpoSc*100).toFixed(0)}${adjStr}
      </button>`;
    }
    const addBtns = "";

    html += `<tr class="prospect-row" ${rowClick} title="${rangeTip}">
      <td style="padding:4px 3px;color:var(--text-secondary);font-size:11px;">${rank}</td>
      <td style="padding:4px 3px;font-weight:600;font-size:13px;">${name}</td>
      <td style="padding:4px 3px;text-align:right;font-size:11px;color:var(--text-secondary);">${p.age != null ? Number(p.age).toFixed(1) : " - "}</td>
      <td style="padding:4px 3px;color:var(--text-secondary);font-size:11px;">${pos}</td>
      <td style="padding:4px 3px;font-size:11px;"><span class="tm-org-cell">${org ? _tmTeamLogo(org) : ""}<span class="tm-org-abbr">${org}</span></span></td>
      <td style="padding:4px 3px;text-align:right;font-size:11px;">${fv}</td>
      <td style="padding:4px 3px;text-align:right;font-weight:800;font-size:13px;color:${tvCol};font-variant-numeric:tabular-nums;">${_tbFmt(tv)}</td>
      <td style="padding:4px 3px;">${_tbCtrlBadge(p)}</td>
      <td style="padding:4px 3px;">${signals}</td>
    </tr>`;
  });
  html += `</tbody></table>${topPager}`;
  wrap.innerHTML = html;
}

// ── Filter chip wiring (called once after first load) ──────────────────────
function _tbWireFilters() {
  const sec = document.getElementById("tradeboard-section");
  if (!sec) return;

  sec.querySelectorAll("[data-tb-pool]").forEach(btn => btn.addEventListener("click", () => {
    _tbPool = btn.dataset.tbPool;
    btn.closest(".filter-group").querySelectorAll(".chip").forEach(b => b.classList.toggle("active", b===btn));
    resetPage("tradeboard");
    _renderTBRows();
  }));
  sec.querySelectorAll("[data-tb-tier]").forEach(btn => btn.addEventListener("click", () => {
    _tbTier = btn.dataset.tbTier;
    btn.closest(".filter-group").querySelectorAll(".chip").forEach(b => b.classList.toggle("active", b===btn));
    resetPage("tradeboard");
    _renderTBRows();
  }));
  sec.querySelectorAll("[data-tb-pos]").forEach(btn => btn.addEventListener("click", () => {
    _tbPos = btn.dataset.tbPos;
    btn.closest(".filter-group").querySelectorAll(".chip").forEach(b => b.classList.toggle("active", b===btn));
    resetPage("tradeboard");
    _renderTBRows();
  }));

  // Text search
  const searchEl = document.getElementById("tb-search");
  if (searchEl) searchEl.addEventListener("input", () => { _tbQ = searchEl.value; resetPage("tradeboard"); _renderTBRows(); });
  const orgSel = document.getElementById("tb-org-filter");
  if (orgSel) orgSel.addEventListener("change", () => { _tbOrg = orgSel.value || "all"; resetPage("tradeboard"); _renderTBRows(); });
  const exactPosSel = document.getElementById("tb-exact-pos-filter");
  if (exactPosSel) exactPosSel.addEventListener("change", () => { _tbExactPos = exactPosSel.value || "all"; resetPage("tradeboard"); _renderTBRows(); });
  const sortSel = document.getElementById("tb-sort-select");
  if (sortSel) sortSel.addEventListener("change", () => { _tbSort = sortSel.value || "trade_desc"; resetPage("tradeboard"); _renderTBRows(); });

  // Mock trade: search boxes
  sec.querySelectorAll(".mock-trade-search").forEach(inp => {
    const side = inp.dataset.side;
    const sug  = sec.querySelector(`.mock-trade-suggestions[data-side="${side}"]`);
    inp.addEventListener("input", () => _mtSearchInput(side, inp.value, sug));
    inp.addEventListener("blur", () => setTimeout(() => { if (sug) sug.style.display = "none"; }, 200));
  });

  // Clear + export buttons
  const clearBtn = document.getElementById("mock-trade-clear");
  if (clearBtn) clearBtn.addEventListener("click", () => {
    _mockTrade.a = []; _mockTrade.b = [];
    ["a","b"].forEach(s => {
      const li = sec.querySelector(`.mock-trade-list[data-side="${s}"]`);
      if (li) li.innerHTML = "";
      const inp = sec.querySelector(`.mock-trade-search[data-side="${s}"]`);
      if (inp) inp.value = "";
    });
    _mtUpdateVerdict();
  });
  const expBtn = document.getElementById("mock-trade-export");
  if (expBtn) expBtn.addEventListener("click", _mtExport);
}

// ── Main entry point ────────────────────────────────────────────────────────
function renderTradeBoard() {
  const wrap = document.getElementById("tradeboard-content");
  if (!wrap) return;
  const base = (typeof DATA_BASE !== "undefined" ? DATA_BASE : "/data/");
  const vp   = (typeof _dataVersion !== "undefined" && _dataVersion)
    ? "?v=" + encodeURIComponent(_dataVersion) : "";

  if (!_tbData) {
    wrap.innerHTML = '<div class="spinner-wrap"><span class="spinner"></span></div>';
    fetch(base + "trade_values.json" + vp, { cache: "no-cache" })
      .then(r => { if (!r.ok) throw new Error(r.status); return r.json(); })
      .then(d => { _tbData = d; window._tbData = d; _tbPopulateSelectFilters(); _renderTBRows(); _tbWireFilters(); })
      .catch(e => {
        wrap.innerHTML = `<div class="empty-state">Trade Board data not found (<code>data/trade_values.json</code>). Run <code>python run_monthly.py --rebuild-only</code> to generate it.<br><small>${e}</small></div>`;
      });
    return;
  }
  _tbPopulateSelectFilters();
  _renderTBRows();
}

// ── Mock Trade Builder logic ────────────────────────────────────────────────
function _mtPlayerByKey(key) {
  return (_tbData && _tbData.players || []).find(p => p.player_key === key) || null;
}

function _mtAdd(side, key) {
  const p = _mtPlayerByKey(key);
  if (!p) return;
  if (_mockTrade[side].some(x => x.player_key === key)) return; // no dupes
  _mockTrade[side].push(p);
  _mtRenderList(side);
  _mtUpdateVerdict();
}

function _mtRemove(side, key) {
  _mockTrade[side] = _mockTrade[side].filter(p => p.player_key !== key);
  _mtRenderList(side);
  _mtUpdateVerdict();
}

function _mtRenderList(side) {
  const sec = document.getElementById("tradeboard-section");
  if (!sec) return;
  const ul    = sec.querySelector(`.mock-trade-list[data-side="${side}"]`);
  const total = sec.querySelector(`.mock-trade-total[data-side="${side}"]`);
  if (!ul) return;
  const players = _mockTrade[side];
  ul.innerHTML = players.map(p => {
    const tv  = p.trade_value_mm;
    const col = _TB_TIER_COLORS[p.trade_value_tier || "low"] || "var(--text-secondary)";
    const isMlb = _tbIsMlb(p);
    return `<li style="display:flex;justify-content:space-between;align-items:center;
                        padding:5px 0;border-bottom:1px solid var(--border-subtle);font-size:12px;">
      <span>
        <strong>${escapeHtml(p.player_name || "?")}</strong>
        <span style="color:var(--text-secondary);margin-left:4px;">${escapeHtml(p.position||"")} · ${escapeHtml(p.org||"")} · ${isMlb?"MLB":"MiLB"} · ${_tbCtrlBadge(p)}</span>
      </span>
      <span style="display:flex;align-items:center;gap:8px;">
        <span style="font-weight:700;color:${col};">${_tbFmt(tv)}</span>
        <button class="chip" style="padding:1px 6px;font-size:10px;"
          onclick="_mtRemove('${escapeHtml(side)}','${escapeHtml(p.player_key||"")}')">✕</button>
      </span>
    </li>`;
  }).join("");
  const sum = players.reduce((acc, p) => acc + (p.trade_value_mm || 0), 0);
  if (total) total.textContent = _tbFmt(sum);
}

function _mtUpdateVerdict() {
  const sec = document.getElementById("tradeboard-section");
  const vd  = document.getElementById("mock-trade-verdict");
  if (!vd) return;
  const sumA = _mockTrade.a.reduce((a, p) => a + (p.trade_value_mm || 0), 0);
  const sumB = _mockTrade.b.reduce((a, p) => a + (p.trade_value_mm || 0), 0);

  if (!_mockTrade.a.length && !_mockTrade.b.length) { vd.style.display = "none"; return; }
  vd.style.display = "block";

  const diff  = sumA - sumB;   // positive = Team A gives more, so Team A receives less value
  const pctDiff = Math.abs(diff) / Math.max(1, Math.min(sumA || 0, sumB || 0)) * 100;

  let verdict = "", color = "var(--neon-green)";

  if (_mockTrade.a.length === 0 || _mockTrade.b.length === 0) {
    verdict = "Add players to both sides to see the grader verdict.";
    color = "var(--text-secondary)";
  } else if (pctDiff < 10) {
    verdict = "✓ Likely fair - both sides within 10% of equal value.";
    color = "var(--neon-green)";
  } else if (pctDiff < 25) {
    if (diff > 0) verdict = `⚠ Team A may hesitate - giving ${_tbFmt(Math.abs(diff))} more than it receives (${pctDiff.toFixed(0)}% gap).`;
    else verdict = `⚠ Team B may hesitate - giving ${_tbFmt(Math.abs(diff))} more than it receives (${pctDiff.toFixed(0)}% gap).`;
    color = "var(--neon-amber)";
  } else if (pctDiff < 60) {
    if (diff > 0) verdict = `✗ Team A likely rejects - giving ${_tbFmt(Math.abs(diff))} more than it receives (${pctDiff.toFixed(0)}% gap). Significant imbalance.`;
    else verdict = `✗ Team B likely rejects - giving ${_tbFmt(Math.abs(diff))} more than it receives (${pctDiff.toFixed(0)}% gap). Significant imbalance.`;
    color = "var(--neon-red)";
  } else {
    if (diff > 0) verdict = `✗✗ Team A definitively rejects - massive overpay (${pctDiff.toFixed(0)}% gap). Trade as structured is not viable.`;
    else verdict = `✗✗ Team B definitively rejects - massive overpay (${pctDiff.toFixed(0)}% gap). Trade as structured is not viable.`;
    color = "var(--neon-red)";
  }

  vd.innerHTML = `<div style="color:${color};font-weight:600;margin-bottom:4px;">${verdict}</div>
    <div style="font-size:11px;color:var(--text-secondary);">
      Team A gives: ${_tbFmt(sumA)} · Team B gives: ${_tbFmt(sumB)} · Gap: ${_tbFmt(Math.abs(diff))}
    </div>`;
}

function _mtSearchInput(side, query, sugEl) {
  if (!sugEl) return;
  const q = (query || "").toLowerCase().trim();
  if (!q || !_tbData) { sugEl.style.display = "none"; return; }
  const matches = (_tbData.players || [])
    .filter(p => (p.player_name || "").toLowerCase().includes(q))
    .slice(0, 12);
  if (!matches.length) { sugEl.style.display = "none"; return; }
  sugEl.style.display = "block";
  sugEl.innerHTML = matches.map(p => {
    const isMlb = _tbIsMlb(p);
    return `<div style="padding:6px 8px;cursor:pointer;border-bottom:1px solid var(--border-subtle);"
                 onmousedown="event.preventDefault();_mtAdd('${escapeHtml(side)}','${escapeHtml(p.player_key||"")}');
                              this.closest('.mock-trade-suggestions').style.display='none';
                              document.querySelector('.mock-trade-search[data-side=\\'${escapeHtml(side)}\\']').value='';">
      <strong>${escapeHtml(p.player_name||"")}</strong>
      <span style="color:var(--text-secondary);font-size:10px;"> ${escapeHtml(p.position||"")} · ${escapeHtml(p.org||"")} · ${isMlb?"MLB":"MiLB"} · ${_tbFmt(p.trade_value_mm)}</span>
    </div>`;
  }).join("");
}

function _mtExport() {
  const fmtSide = (side) => _mockTrade[side].map(p =>
    ` ${p.player_name} (${p.position}, ${p.org}, ${_tbIsMlb(p)?"MLB":"MiLB"}) - ${_tbFmt(p.trade_value_mm)}`
  ).join("\n");
  const sumA = _mockTrade.a.reduce((a,p)=>a+(p.trade_value_mm||0),0);
  const sumB = _mockTrade.b.reduce((a,p)=>a+(p.trade_value_mm||0),0);
  const text = `=== Mock Trade (eephus.io Trade Board) ===\n\nTeam A receives:\n${fmtSide("b")||"  (none)"}\n  Total: ${_tbFmt(sumB)}\n\nTeam B receives:\n${fmtSide("a")||"  (none)"}\n  Total: ${_tbFmt(sumA)}\n\nGap: ${_tbFmt(Math.abs(sumA-sumB))}`;
  navigator.clipboard ? navigator.clipboard.writeText(text).then(() => alert("Copied to clipboard!"))
                      : prompt("Copy this trade:", text);
}
// ── GRPO Group Panel ────────────────────────────────────────────────────────
// Shows the "profile group" for a given player - all active prospects sharing
// the same position × level × age_tier × power_tier cluster.
// The GRPO model ranks them by within-group breakout probability, so this is
// effectively a "next Jesús Made" finder for any player.
function _tbShowGroup(playerKey) {
  if (!_tbData) return;
  const panel = document.getElementById("tb-group-panel");
  const title = document.getElementById("tb-group-title");
  const body  = document.getElementById("tb-group-body");
  if (!panel || !title || !body) return;

  const pScore = (_tbData.all_scores || {})[playerKey];
  if (!pScore) { panel.style.display = "none"; return; }

  const members = pScore.active_group_members || [];
  const grp     = pScore.group || "?";
  const anchor  = pScore.player_name || playerKey;

  title.innerHTML = `GRPO group for <strong>${escapeHtml(anchor)}</strong>
    <span style="font-weight:400;color:var(--text-secondary);font-size:11px;margin-left:8px;">${escapeHtml(grp)}</span>`;

  if (!members.length) {
    body.innerHTML = `<div style="color:var(--text-secondary);font-size:12px;">No other active prospects in this group yet.</div>`;
  } else {
    const rows = members.map((m, i) => {
      const bs = m.breakout_score != null ? (m.breakout_score * 100).toFixed(0) + "%" : " - ";
      const bsCol = (m.breakout_score || 0) >= 0.60 ? "var(--neon-green)" : (m.breakout_score || 0) >= 0.45 ? "var(--neon-amber)" : "var(--text-secondary)";
      const avl = m.age_vs_level != null ? `${m.age_vs_level > 0 ? "+" : ""}${Number(m.age_vs_level).toFixed(1)}yr` : " - ";
      return `<tr style="font-size:12px;" class="prospect-row"
                  onclick="goToPlayer('${escapeHtml(m.player_key||'')}');"
                  style="cursor:pointer;">
        <td style="padding:4px 6px;color:var(--text-secondary);">${i + 1}</td>
        <td style="padding:4px 6px;font-weight:600;">${escapeHtml(m.player_name || "?")}</td>
        <td style="padding:4px 6px;color:var(--text-secondary);">${escapeHtml(m.position || "")}</td>
        <td style="padding:4px 6px;color:var(--text-secondary);">${escapeHtml(m.org || "")}</td>
        <td style="padding:4px 6px;text-align:right;">${m.fv != null ? Number(m.fv).toFixed(0) : " - "}</td>
        <td style="padding:4px 6px;text-align:right;">${m.age != null ? Number(m.age).toFixed(1) : " - "}</td>
        <td style="padding:4px 6px;">${escapeHtml(m.current_level || "")}</td>
        <td style="padding:4px 6px;color:var(--text-secondary);font-size:10px;">${avl}</td>
        <td style="padding:4px 6px;text-align:right;font-weight:600;color:${bsCol};">${bs}</td>
      </tr>`;
    }).join("");
    body.innerHTML = `<div style="font-size:11px;color:var(--text-secondary);margin-bottom:6px;">
        Profile matches: ${escapeHtml(grp.replace(/\|/g, " · "))} · ranked by GRPO breakout score
      </div>
      <table style="width:100%;border-collapse:collapse;">
        <thead><tr style="font-size:10px;color:var(--text-secondary);">
          <th style="padding:3px 6px;">#</th><th style="padding:3px 6px;">Player</th>
          <th style="padding:3px 6px;">Pos</th><th style="padding:3px 6px;">Org</th>
          <th style="padding:3px 6px;text-align:right;">FV</th>
          <th style="padding:3px 6px;text-align:right;">Age</th>
          <th style="padding:3px 6px;">Lvl</th>
          <th style="padding:3px 6px;">Age△</th>
          <th style="padding:3px 6px;text-align:right;">G-score</th>
        </tr></thead>
        <tbody>${rows}</tbody>
      </table>`;
  }

  // Historical comps from training set
  const histComps = pScore.comps || [];
  if (histComps.length) {
    const hRows = histComps.map(c => {
      const outcome = c.outcome != null ? (c.outcome * 100).toFixed(0) + "%" : " - ";
      const warStr = c.war_per_yr != null ? `${Number(c.war_per_yr).toFixed(2)} WAR/yr` : " - ";
      return `<tr style="font-size:11px;">
        <td style="padding:3px 6px;font-weight:600;">${escapeHtml(c.player_name || "?")}</td>
        <td style="padding:3px 6px;color:var(--text-secondary);">FV ${c.fv != null ? Number(c.fv).toFixed(0) : " - "}</td>
        <td style="padding:3px 6px;color:var(--text-secondary);">${warStr}</td>
        <td style="padding:3px 6px;text-align:right;color:var(--text-secondary);">${outcome} outcome</td>
      </tr>`;
    }).join("");
    body.innerHTML += `<div style="margin-top:10px;font-size:11px;color:var(--text-secondary);font-weight:600;">Historical comps (most similar graduates):</div>
      <table style="width:100%;border-collapse:collapse;">${hRows}</table>`;
  }

  panel.style.display = "block";
  panel.scrollIntoView({ behavior: "smooth", block: "nearest" });
}
// ─── end Trade Board ──────────────────────────────────────────────────────────


  // ---- data bootstrap + mount ------------------------------------------------
  // The evaluator values prospects on trade_values.json posterior surplus and MLB
  // players on mlb_player_detail.json projection surplus - the same "one currency"
  // the PROSPX module used, sourced from standalone files here.
  function _tmBuildProspectPool(d) {
    DATA.players = (d.players || [])
      .filter(p => p && !_tbIsMlb(p) && p.posterior_surplus_mm != null)
      .map(p => ({
        player_key: p.player_key, player_name: p.player_name,
        position: p.position, org: p.org, fv_close: p.fv,
        surplus: { value_mm: p.posterior_surplus_mm }
      }));
  }

  let _mounted = false;
  function mount() {
    if (_mounted) { renderTradeMachine(); _renderTBRows(); return; }
    if (!document.getElementById("tradeboard-content")) return;
    _mounted = true;
    fetch(DATA_BASE + "trade_values.json", { cache: "no-cache" })
      .then(r => { if (!r.ok) throw new Error(r.status); return r.json(); })
      .then(d => {
        _tbData = d; window._tbData = d;
        _tmBuildProspectPool(d);
        _tbPopulateSelectFilters();
        _renderTBRows();
        _tbWireFilters();
        renderTradeMachine();   // also fetches MLB detail + seeds from #tm=
      })
      .catch(() => {
        const w = document.getElementById("tradeboard-content");
        if (w) w.innerHTML = '<div class="empty-state">Trade-value data not found '
          + '(<code>data/trade_values.json</code>). Run <code>python run_monthly.py --rebuild-only</code>.</div>';
      });
  }

  window.TradeMachine = { mount: mount };
})();
