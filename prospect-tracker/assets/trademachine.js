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

  // The PROSPX->/projections/ relocation dropped resetPage() + the global page-chip
  // delegation, so the Trade Board's filters reset nothing and its pager did nothing.
  // Both are restored here, self-contained.
  function resetPage(key) {
    if (state.pages && (state.pages[key] || 1) !== 1) state.pages[key] = 1;
  }
  document.addEventListener("click", (e) => {
    const btn = e.target && e.target.closest && e.target.closest("[data-tradeboard-page]");
    if (!btn || btn.disabled) return;
    const n = Math.max(1, parseInt(btn.getAttribute("data-tradeboard-page"), 10) || 1);
    state.pages = state.pages || {};
    if ((state.pages.tradeboard || 1) === n) return;
    const clicked = btn.closest(".pg-strip");
    const before = Array.from(document.querySelectorAll(".pg-strip"));
    const idx = clicked ? before.indexOf(clicked) : -1;
    state.pages.tradeboard = n;
    _renderTBRows();
    requestAnimationFrame(() => {
      const after = document.querySelectorAll(".pg-strip");
      const t = (idx >= 0 && idx < after.length) ? after[idx] : after[0];
      if (t && t.scrollIntoView) t.scrollIntoView({ block: "nearest", behavior: "smooth" });
    });
  });

  // In PROSPX, clicking a board player opens an in-app detail; here we deep-link
  // back to that prospect's PROSPX page.
  function renderPlayerDetail(key) {
    if (key) location.href = "/prospx/#player=" + encodeURIComponent(key);
  }
  // Board / group-panel navigation. MLB players (debuted/graduated) deep-link to
  // their MLB Projections page; prospects to their PROSPX page. The board rows
  // used to call goToPlayer(), a PROSPX global that does not exist in the
  // /projections/ app, so clicks silently no-op'd - this gives every row a
  // working, correctly-routed destination.
  function _tmNavPlayer(key, isMlb) {
    if (!key) return;
    location.href = (isMlb ? "/projections/#player=" : "/prospx/#player=") + encodeURIComponent(key);
  }
  window._tmNavPlayer = _tmNavPlayer;   // referenced from inline row onclick handlers
  // Same trap as _tmNavPlayer: the GRPO breakout chip's inline onclick resolves
  // against the global scope, not this IIFE's closure - without this export the
  // chip threw ReferenceError and the group panel never opened. (Function
  // declarations hoist, so assigning here is safe.)
  window._tbShowGroup = _tbShowGroup;
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
      <span class="pg-count">Showing ${lo}-${hi} of ${totalItems}</span>
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
    if (sv != null) { _TM.a.push({ kind: "prospect", key, name: p.player_name, pos: p.position || "", org: p.org || "",
      sub: `${p.position || ""} · ${p.org || ""} · FV ${p.fv_close ?? "?"}`, mm: sv }); _TM.seeded = true; }
  } else if (kind === "mlb") {
    if (!_TM.detail) return;                 // detail still loading; seed on the re-render
    const d = _TM.detail[key];
    if (d && d.proj && d.proj.surNpv != null) _TM.a.push({ kind: "mlb", key, name: d.name, pos: d.pos || "", org: d.team || "",
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
    const list = _TM[side].map((x, i) => {
      const g = _tbGrade(x.mm), gc = _tbGradeColor(g);   // contract-adjusted surplus -> letter
      return `
      <div class="tm-row">
        <span class="tm-kind tm-kind--${x.kind}" title="${x.kind === "prospect" ? "Prospect (eFV surplus)" : "MLB (contract surplus)"}">${x.kind === "prospect" ? "P" : "M"}</span>
        ${_tmTeamLogo(x.org)}
        <a class="fa-player-link tm-name" href="${x.kind === "prospect" ? `/prospx/#player=${encodeURIComponent(x.key)}` : `/projections/#player=${encodeURIComponent(x.key)}`}">${escapeHtml(x.name)}</a>
        <span class="tm-sub">${escapeHtml(x.pos || "")}</span>
        ${g ? `<span class="tm-grade-chip" style="color:${gc};border-color:${gc};" title="Trade Value Grade ${g} (contract-adjusted surplus)">${g}</span>` : ""}
        <span class="tm-val" style="color:${_tmValColor(x.mm)};">${x.mm >= 0 ? "$" : "-$"}${Math.abs(x.mm).toFixed(1)}M</span>
        <button class="tm-x" data-tm-remove="${side}:${i}" title="Remove">×</button>
      </div>`;
    }).join("");
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
  const bothSides = _TM.a.length && _TM.b.length;
  // Split the balance bar on each side's value relative to the combined range,
  // shifting by the more-negative side so the ordering matches the verdict even
  // when BOTH sides are net-negative (the more-negative side shows as the worse).
  const balBase = Math.min(0, dA, dB);
  const aShift = dA - balBase, bShift = dB - balBase, shiftSum = aShift + bShift;
  const aPct = shiftSum > 0 ? Math.round(100 * aShift / shiftSum) : 50;
  const diff = Math.abs(dA - dB);
  const lead = dA >= dB ? "A" : "B";
  const behind = lead === "A" ? "B" : "A";
  const pct = diff / Math.max(1, Math.abs(dA), Math.abs(dB)) * 100;
  // Graduated accept/reject grader (merged in from the old Mock Trade Builder), in the
  // evaluator's "receives" framing: the side that RECEIVES less value is the one giving up
  // the edge, so it is the side that hesitates / rejects.
  let vClass = "is-bal", vText = "";
  if (!bothSides) { vText = "Add players to both sides for the grader verdict."; vClass = ""; }
  else if (diff < BALANCED_THRESHOLD_MM) { vText = `✓ Likely fair: both sides within $${BALANCED_THRESHOLD_MM}M.`; vClass = "is-bal"; }
  else if (pct < 15) { vText = `✓ Fair: Side ${lead} +$${diff.toFixed(1)}M (${pct.toFixed(0)}% edge).`; vClass = "is-bal"; }
  else if (pct < 40) { vText = `⚠ Side ${behind} may hesitate: $${diff.toFixed(1)}M short (${pct.toFixed(0)}% gap).`; vClass = "is-warn"; }
  else if (pct < 70) { vText = `✗ Side ${behind} likely rejects: $${diff.toFixed(1)}M gap (${pct.toFixed(0)}%).`; vClass = "is-bad"; }
  else { vText = `✗✗ Lopsided: Side ${behind} won't do this (${pct.toFixed(0)}% gap).`; vClass = "is-bad"; }
  const verdict = have
    ? `<div class="tm-verdict">
         <div class="tm-balbar" title="value split A vs B">
           <div class="tm-balbar-a" style="width:${aPct}%"></div>
           <div class="tm-balbar-b" style="width:${100 - aPct}%"></div>
         </div>
         <div class="tm-balrow">
           <span class="tm-balverdict ${vClass}">${vText}</span>
           <span class="fa-sub">one currency: prospect surplus (control-window NPV) + MLB contract surplus</span>
         </div>
         <div class="tm-controls">
           <button class="chip" data-tm-clear type="button">Clear</button>
           <button class="chip" data-tm-copy type="button">Copy as text</button>
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
           <span class="tm-val">${window.EEPHUS_HUB.money(h.mm)}</span></button>`).join("");
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
  const clearB = el.querySelector("[data-tm-clear]");
  if (clearB) clearB.onclick = () => { _TM.a = []; _TM.b = []; renderTradeMachine(); };
  const copyB = el.querySelector("[data-tm-copy]");
  if (copyB) copyB.onclick = () => {
    const fmt = side => _TM[side].map(x =>
      ` ${x.name} (${[x.pos, x.org].filter(Boolean).join(", ")}${x.org || x.pos ? ", " : ""}${x.kind === "prospect" ? "prospect" : "MLB"}) ${x.mm >= 0 ? "$" : "-$"}${Math.abs(x.mm).toFixed(1)}M`
    ).join("\n");
    const text = `=== Trade Machine (eephus.io) ===\n\nSide A receives:\n${fmt("a") || "  (none)"}\n  Total: $${dA.toFixed(1)}M\n\nSide B receives:\n${fmt("b") || "  (none)"}\n  Total: $${dB.toFixed(1)}M\n\nGap: $${Math.abs(dA - dB).toFixed(1)}M`;
    const done = () => { copyB.textContent = "Copied!"; setTimeout(() => { copyB.textContent = "Copy as text"; }, 1300); };
    if (navigator.clipboard) navigator.clipboard.writeText(text).then(done, () => prompt("Copy this trade:", text));
    else prompt("Copy this trade:", text);
  };
}

// ─── Trade Board ──────────────────────────────────────────────────────────────
let _tbData   = null;   // also exposed as window._tbData for renderPlayerDetail fallback
// GRPO group-panel sidecar availability. The full internals file
// (grpo_scores.json) never ships (deploy/data_exclude.txt bars it), so we
// fetch the slim public sidecar grpo_public.json instead - the projection
// export_grpo_scores emits alongside the full file with only the fields the
// panel renders. Until a deployment's pipeline has emitted it, the fetch can
// 404 - track it so a chip click can say so honestly instead of silently
// doing nothing. Never add a fallback fetch to the excluded full file.
let _tbGrpoState = "pending";   // "pending" | "ready" | "unavailable"
let _tbPool   = "all";
let _tbTier   = "all";
let _tbPos    = "all";
let _tbOrg    = "all";
let _tbExactPos = "all";
let _tbSort   = "trade_desc";
let _tbQ      = "";        // free-text search

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
// Parse the _tbSort string into [column, direction]. "trade_desc" (the legacy
// default + dropdown value) maps to the surplus column so header clicks and the
// dropdown share one model.
function _tbSortParts() {
  if (_tbSort === "trade_desc" || !_tbSort) return ["grade", "desc"];
  const i = _tbSort.lastIndexOf("_");
  if (i < 0) return [_tbSort, "desc"];
  return [_tbSort.slice(0, i), _tbSort.slice(i + 1)];
}
// Per-column accessor (numeric -> null when absent so nulls always sort last;
// text -> string). The default Grade column ranks by the raw eFV grade
// (xfv_grade), which orders realized WAR better than the $-surplus transform
// (data/trade_machine_eval.json: grade rho 0.3433 vs surplus 0.3289, and grade
// wins within every tier). Note: since the 2026-07-06 quantile flip, surplus
// dollars are priced on the DISPLAYED quantile grade, not this raw grade -
// they are related but distinct orderers. Surplus stays on trade_value_mm.
function _tbSortVal(p, col) {
  const num = v => (v == null || v === "") ? null : (Number.isFinite(Number(v)) ? Number(v) : null);
  if (col === "age") return { n: num(p.age) };
  if (col === "fv")  return { n: num(p.fv) };
  if (col === "org") return { t: String(p.org || "") };
  if (col === "pos") return { t: _tbPrimaryPos(p.position) };
  if (col === "name") return { t: String(p.player_name || "") };
  if (col === "contract") return { n: num(p.remaining_control_years) };
  if (col === "risk") return { n: num(p.sortino) };   // downside-adjusted surplus
  if (col === "surplus") return { n: num(p.trade_value_mm) };   // explicit $ column
  return { n: num(p.xfv_grade) };                // grade (default) - eFV grade orderer
}
function _tbSortRows(rows) {
  const [col, dir] = _tbSortParts();
  const sign = dir === "asc" ? 1 : -1;
  const tv = p => { const v = Number(p.trade_value_mm); return Number.isFinite(v) ? v : -1e9; };
  // Cross-key tiebreaks: surplus $ then eFV grade. The default Grade column now
  // ranks by xfv_grade directly (see _tbSortVal); the explicit Surplus column
  // ranks by trade_value_mm and falls to xfv_grade to break the large low/fringe
  // block the convex-$/WAR + $0-floor surplus transform bunches at one value.
  const xg = p => { const v = Number(p.xfv_grade); return Number.isFinite(v) ? v : -1e9; };
  rows.sort((a, b) => {
    const av = _tbSortVal(a, col), bv = _tbSortVal(b, col);
    let c;
    if ("t" in av) {                             // text column
      c = av.t.localeCompare(bv.t) * sign;
    } else {                                     // numeric column - nulls always last
      if (av.n == null && bv.n == null) c = 0;
      else if (av.n == null) c = 1;
      else if (bv.n == null) c = -1;
      else c = (av.n - bv.n) * sign;
    }
    return c || (tv(b) - tv(a)) || (xg(b) - xg(a));   // surplus desc, then eFV grade desc
  });
  return rows;
}
// Render a clickable, sort-aware column header with an active-direction arrow.
function _tbTh(label, col, cls, title, noActiveMark) {
  const [scol, sdir] = _tbSortParts();
  const active = !noActiveMark && scol === col;
  const arrow = active ? (sdir === "asc" ? " ▲" : " ▼") : "";
  const classes = ["tm-sortable", cls, active ? "tm-sorted" : ""].filter(Boolean).join(" ");
  const tt = (title ? title + " · " : "") + "click to sort";
  const ariaSort = active ? (sdir === "asc" ? "ascending" : "descending") : "none";
  return `<th class="${classes}" data-tb-sortcol="${col}" title="${tt}" tabindex="0" role="button" aria-sort="${ariaSort}">${label}${arrow}</th>`;
}
// Column header click: toggle direction if already sorted by it, else pick a
// sensible default (text asc, numeric desc).
function _tbSortByCol(col) {
  const [scol, sdir] = _tbSortParts();
  // First click default: ascending for text + age (youngest first is the useful
  // default on a prospect board); descending for value-like columns (best first).
  const dir = (scol === col) ? (sdir === "asc" ? "desc" : "asc")
            : (["name", "org", "pos", "age"].includes(col) ? "asc" : "desc");
  _tbSort = `${col}_${dir}`;
  const sel = document.getElementById("tb-sort-select");
  if (sel) { const opt = (_tbSort === "grade_desc" || _tbSort === "surplus_desc") ? "trade_desc" : _tbSort; sel.value = opt; if (sel.value !== opt) sel.selectedIndex = -1; }
  resetPage("tradeboard");
  _renderTBRows();
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
// § CRUNCH chip: flags roster-decision exposure (Rule 5 must-protect, out of
// options on the 40-man). Reads the compact crunch sub-dict on each board row.
function _tbCrunchChip(c) {
  if (!c) return "";
  const bits = [];
  if (c.rule5_exposed) bits.push("R5");
  if (c.on_40_man && c.options_left === 0) bits.push("0-opt");
  else if (c.on_40_man && c.options_left === 1) bits.push("1-opt");
  if (!bits.length) return "";
  const sc = c.score || 0;
  const col = sc >= 55 ? "var(--neon-red)" : sc >= 30 ? "var(--neon-amber)" : "var(--text-secondary)";
  const tip = `Roster crunch ${sc}: ${c.rule5_exposed ? "Rule 5 exposed this November; " : ""}`
    + `${c.on_40_man ? "on the 40-man" : "off the 40-man"} · ${c.options_left} option${c.options_left === 1 ? "" : "s"} left`
    + `${c.service_phase && c.service_phase !== "none" ? " · " + escapeHtml(c.service_phase) : ""}`;
  return ` <span class="chip" style="padding:1px 5px;font-size:9px;color:${col};border-color:${col};" title="${tip}">${bits.join(" ")}</span>`;
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
  if (mm == null) return "-";
  const a = Math.abs(Number(mm));
  const sign = mm < 0 ? "-$" : "$";   // surplus can be negative (overpaid MLB contracts)
  return a >= 100 ? `${sign}${a.toFixed(0)}M` : `${sign}${a.toFixed(1)}M`;
}

// Trade Value Grade. Contract-adjusted surplus $M -> letter (A+ .. F). The
// surplus already nets salary out of projected production, so the grade reads
// "how valuable is this player to acquire in trade." Mirrors the Python
// bayes_trade_value._trade_value_grade cutoffs exactly; computed client-side off
// trade_value_mm so it stays in lock-step with the displayed Surplus even if a
// shipped artifact predates the server-side trade_value_grade field.
function _tbGrade(mm) {
  if (mm == null || !isFinite(Number(mm))) return "";
  const v = Number(mm);
  if (v >= 100) return "A+";
  if (v >= 60)  return "A";
  if (v >= 40)  return "A-";
  if (v >= 25)  return "B+";
  if (v >= 15)  return "B";
  if (v >= 8)   return "B-";
  if (v >= 3)   return "C";
  if (v >= 0)   return "D";
  return "F";
}
function _tbGradeColor(g) {
  if (g === "A+" || g === "A") return "var(--card-gold)";
  if (g === "A-")              return "var(--neon-green)";
  if (g && g.charAt(0) === "B") return "var(--neon-cyan, var(--accent-cyan))";
  if (g === "C" || g === "D")  return "var(--text-secondary)";
  if (g === "F")               return "var(--neon-red)";
  return "var(--text-tertiary)";
}

// ── Leaderboard render ──────────────────────────────────────────────────────
// Risk-adjusted surplus (Sortino) column: dark by default pre-launch; opt in
// with #risk=1 for the soak, then flip RISK_UI_DEFAULT at launch. Also degrades
// on payload presence (older exports carry no sortino field).
const RISK_UI_DEFAULT = true;   // surfaced: Risk column on by default (#risk=0 to hide)
function _tbRiskUiOn() {
  const v = new URLSearchParams((location.hash || "").replace(/^#/, "")).get("risk");
  return v != null ? v !== "0" : RISK_UI_DEFAULT;
}
// One compact risk cell: Sortino (upside cushion per unit downside, higher is
// safer) with a tooltip carrying the downside deviation, risk-adjusted surplus,
// and bust probability. Colored by bust risk.
function _tbRiskCell(p) {
  if (p.sortino == null) return `<td class="tm-num tm-dim">-</td>`;
  const pb = p.p_bust;
  const col = pb == null ? "var(--text-secondary)"
    : pb >= 0.25 ? "var(--neon-red)" : pb <= 0.10 ? "var(--neon-green)" : "var(--text-primary)";
  const tip = [
    `Sortino ${p.sortino}: expected surplus per unit of downside risk (higher is safer)`,
    p.risk_mm != null ? `Risk-adjusted surplus $${p.risk_mm}M` : "",
    p.downside_mm != null ? `Downside deviation $${p.downside_mm}M` : "",
    pb != null ? `Bust probability ${(pb * 100).toFixed(0)}%` : "",
  ].filter(Boolean).join(" · ");
  const bustStr = pb != null ? ` <span class="tm-dim" style="font-size:9px;">${(pb * 100).toFixed(0)}% bust</span>` : "";
  return `<td class="tm-num tm-risk" title="${escapeHtml(tip)}"><span style="color:${col};">${p.sortino}</span>${bustStr}</td>`;
}

function _renderTBRows() {
  const wrap = document.getElementById("tradeboard-content");
  if (!wrap || !_tbData) return;
  const q = _tbQ.toLowerCase().trim();
  const showRisk = _tbRiskUiOn() && (_tbData.players || []).some(p => p && p.sortino != null);

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

  // Per-org roster-crunch summary (only when an org is selected). Counts among
  // this org's rostered / MLB board players; disclosed as not a full 40-man census.
  let _crunchBanner = "";
  if (_tbOrg !== "all") {
    const mustProtect = rows.filter(p => p.crunch && p.crunch.rule5_exposed).length;
    const squeezed    = rows.filter(p => p.crunch && p.crunch.on_40_man && p.crunch.options_left === 0).length;
    if (mustProtect || squeezed) {
      _crunchBanner = `<div style="margin:2px 0 6px;color:var(--text-secondary);font-size:11px;" title="Roster-decision exposure among this org's rostered / MLB board players (not a full 40-man census, and not a predictive model)."><strong>${escapeHtml(_tbOrg)} roster crunch:</strong> ${mustProtect} Rule 5 must-protect · ${squeezed} out-of-options on the 40-man</div>`;
    }
  }

  let html = `<div style="margin:6px 0 4px;color:var(--text-secondary);font-size:11px;">${rows.length} players · ${escapeHtml(_tbData.generated_at || "")}</div>
  ${_crunchBanner}
  ${topPager}
  <div class="tm-board-tablewrap"><table class="stats-table tm-board-table">
  <thead><tr>
    <th>#</th>
    ${_tbTh("Player", "name")}
    ${_tbTh("Age", "age", "tm-num", "Current age (decimal years)")}
    ${_tbTh("Pos", "pos")}
    ${_tbTh("Org", "org")}
    ${_tbTh("FV", "fv", "tm-num", "Future Value grade (prospects only - hidden for MLB players where FV is no longer relevant)")}
    ${_tbTh("Grade", "grade", "tm-num tm-col-div", "Trade Value Grade - the contract-adjusted surplus on an A+ to F scale. The board ranks by the model's raw eFV grade, which orders realized value better than the dollar transform; the letter is the coarse display.", true)}
    ${_tbTh("Surplus", "surplus", "tm-num", "Surplus value ($M of production above cost) - the same value_framework model PROSPX and MLB Projections use")}
    ${showRisk ? _tbTh("Risk", "risk", "tm-num", "Sortino: expected surplus per unit of downside risk (higher is safer). Tooltip carries the risk-adjusted surplus and bust probability.") : ""}
    ${_tbTh("Contract", "contract", "", "Contract: phase · salary · FA year (MLB) or remaining controlled seasons (MiLB)")}
    <th class="tm-col-div">Signals</th>
  </tr></thead><tbody>`;

  pagedRows.forEach((p, i) => {
    const rank = (curPage - 1) * pageSize + i + 1;
    const tv    = p.trade_value_mm;
    const tier  = p.trade_value_tier || "low";
    const tvCol = _TB_TIER_COLORS[tier] || "var(--text-secondary)";
    const grade = _tbGrade(tv);              // contract-adjusted surplus -> letter
    const gradeCol = _tbGradeColor(grade);
    // FV only meaningful for active MiLB prospects - hide for MLB players
    const isProspect = p.status === "active";
    const fv    = isProspect && p.fv != null ? String(Math.ceil(Number(p.fv))) : "";
    // Position: trade_values.json now carries fielding-corrected position
    const pos   = escapeHtml(p.position || "");
    const org   = escapeHtml(p.org || "");   // may be empty for some players
    const name  = escapeHtml(p.player_name || "?");
    const isMlb = _tbIsMlb(p);
    const statusCol = isMlb ? "var(--neon-violet)" : "var(--neon-green)";
    const statusLbl = isMlb ? "MLB" : "MiLB";
    const lo = p.trade_value_lo, hi = p.trade_value_hi;
    const rangeTip = (lo != null && hi != null) ? `Range: $${lo}-$${hi}M` : "";
    const flash = p.flash || {};
    const injD  = p.injury_discount || 0;

    // Navigate to player detail: MLB players -> their MLB Projections page,
    // prospects -> their PROSPX page. If no key, no navigation. The whole row
    // stays clickable as a convenience, but the player name is a REAL anchor so
    // keyboard and screen-reader users can reach the player page too (the row
    // onclick preventDefaults the anchor and routes to the same destination).
    const href = p.player_key
      ? (isMlb ? "/projections/#player=" : "/prospx/#player=") + encodeURIComponent(p.player_key)
      : "";
    const rowClick = p.player_key
      ? `onclick="event.preventDefault();_tmNavPlayer('${escapeHtml(p.player_key)}',${isMlb});" style="cursor:pointer;"`
      : "";

    // Signals: status badge + ceiling flag + injury warning + GRPO breakout badge.
    let signals = `<span style="color:${statusCol};font-size:10px;">${statusLbl}</span>`;
    if (flash.is_bimodal) signals += ` <span style="color:var(--card-gold);font-size:10px;" title="Ceiling player (p_click=${flash.p_click})">↑</span>`;
    if (injD > 0.05)      signals += ` <span style="color:var(--neon-red);font-size:10px;" title="Injury discount ${(injD*100).toFixed(0)}%">⚕</span>`;
    signals += _tbCrunchChip(p.crunch);
    // GRPO breakout badge - a within-cohort breakout SIGNAL (display only; it no longer
    // shifts the surplus, which is now the platform eFV/Projections value). Click -> group.
    const grpoSc = p.grpo_breakout_score;
    if (grpoSc != null && grpoSc >= 0.55) {   // only flag genuine breakout signals
      const grpoCol = grpoSc >= 0.70 ? "var(--neon-green)" : "var(--neon-amber)";
      signals += ` <button class="chip" style="padding:1px 5px;font-size:9px;color:${grpoCol};border-color:${grpoCol};"
        onclick="event.stopPropagation();_tbShowGroup('${escapeHtml(p.player_key||'')}');"
        title="Breakout signal: ${(grpoSc*100).toFixed(0)}% within-cohort breakout score (provisional; does not change the surplus) - click to see the profile group">
        ▲${(grpoSc*100).toFixed(0)}
      </button>`;
    }
    const addBtns = "";

    html += `<tr class="prospect-row" ${rowClick} title="${rangeTip}">
      <td class="tm-rank">${rank}</td>
      <td class="tm-player">${href ? `<a class="fa-player-link" href="${href}">${name}</a>` : name}</td>
      <td class="tm-num tm-dim">${p.age != null ? Number(p.age).toFixed(1) : "-"}</td>
      <td class="tm-dim">${pos}</td>
      <td><span class="tm-org-cell">${org ? _tmTeamLogo(org) : ""}<span class="tm-org-abbr">${org}</span></span></td>
      <td class="tm-num tm-dim">${fv}</td>
      <td class="tm-num tm-col-div tm-grade">${grade ? `<span class="tm-grade-chip" style="color:${gradeCol};border-color:${gradeCol};" title="Trade Value Grade ${grade} (${_tbFmt(tv)} contract-adjusted surplus)">${grade}</span>` : ""}</td>
      <td class="tm-num tm-surplus" style="color:${tvCol};">${_tbFmt(tv)}</td>
      ${showRisk ? _tbRiskCell(p) : ""}
      <td class="tm-contract">${_tbCtrlBadge(p)}</td>
      <td class="tm-col-div tm-signals">${signals}</td>
    </tr>`;
  });
  // The wrapper div is the host the universal copy/export chip attaches to
  // (eephus-export.js puts the chip on the table's PARENT), keeping the chip
  // pinned to the table instead of the whole board pane.
  html += `</tbody></table></div>${topPager}`;
  wrap.innerHTML = html;
  // Sortable column headers (the table is rebuilt each render, so rewire here).
  wrap.querySelectorAll("th[data-tb-sortcol]").forEach(th => {
    th.addEventListener("click", () => _tbSortByCol(th.dataset.tbSortcol));
    th.addEventListener("keydown", e => {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); _tbSortByCol(th.dataset.tbSortcol); }
    });
  });
}

// ── Filter chip wiring (called once after first load) ──────────────────────
function _tbWireFilters() {
  // The Trade Machine view scaffold root (was #tradeboard-section in PROSPX; the
  // relocation renamed it, which silently broke every filter -- sec was null here).
  const sec = document.getElementById("proj-view-trademachine");
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
      .then(d => {
        _tbData = d; window._tbData = d; _tbPopulateSelectFilters(); _renderTBRows(); _tbWireFilters();
        // GRPO group-panel data lives in the slim public sidecar; merge it so the
        // ▲## breakout chip's _tbShowGroup() can resolve. Non-blocking: the board is
        // already rendered. Before a deployment's first pipeline run emits the
        // sidecar, this 404s - an expected outcome, not an error - so mark it
        // unavailable and degrade in the panel.
        fetch(base + "grpo_public.json" + vp, { cache: "no-cache" })
          .then(r => r.ok ? r.json() : null)
          .then(g => {
            if (g && g.all_scores && _tbData) { _tbData.all_scores = g.all_scores; _tbGrpoState = "ready"; }
            else { _tbGrpoState = "unavailable"; }
          })
          .catch(() => { _tbGrpoState = "unavailable"; });
      })
      .catch(e => {
        wrap.innerHTML = `<div class="empty-state">This view is temporarily unavailable. Check back shortly.</div>`;
      });
    return;
  }
  _tbPopulateSelectFilters();
  _renderTBRows();
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
  if (!pScore) {
    // Honest degrade: the group sidecar may still be loading, or this
    // deployment does not publish it at all - say so instead of a dead click.
    title.textContent = "GRPO profile group";
    body.innerHTML = `<div style="color:var(--text-secondary);font-size:12px;">${
      _tbGrpoState === "pending"
        ? "Group data is still loading. Try the chip again in a moment."
        : "Profile-group details are not available here right now. The breakout score on the chip still stands."
    }</div>`;
    panel.style.display = "block";
    panel.scrollIntoView({ behavior: "smooth", block: "nearest" });
    return;
  }

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
      const mHref = m.player_key ? "/prospx/#player=" + encodeURIComponent(m.player_key) : "";
      const mName = escapeHtml(m.player_name || "?");
      return `<tr style="font-size:12px;cursor:pointer;" class="prospect-row"
                  onclick="_tmNavPlayer('${escapeHtml(m.player_key||'')}',false);">
        <td style="padding:4px 6px;color:var(--text-secondary);">${i + 1}</td>
        <td style="padding:4px 6px;font-weight:600;">${mHref ? `<a class="fa-player-link" href="${mHref}">${mName}</a>` : mName}</td>
        <td style="padding:4px 6px;color:var(--text-secondary);">${escapeHtml(m.position || "")}</td>
        <td style="padding:4px 6px;color:var(--text-secondary);">${escapeHtml(m.org || "")}</td>
        <td style="padding:4px 6px;text-align:right;">${m.fv != null ? String(Math.ceil(Number(m.fv))) : " - "}</td>
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
        <td style="padding:3px 6px;color:var(--text-secondary);">FV ${c.fv != null ? String(Math.ceil(Number(c.fv))) : " - "}</td>
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

  // Wire the "Filter & Sort" collapsible toggle on the /projections/ page (the
  // generic [data-collapse-target] handler only ships inside the PROSPX app).
  // Scoped to #proj-view-trademachine so prospx is untouched.
  let _filterToggleWired = false;
  function _tbWireFilterToggle() {
    if (_filterToggleWired) return;
    const tBtn = document.querySelector('#proj-view-trademachine [data-collapse-target]');
    if (!tBtn) return;
    _filterToggleWired = true;
    tBtn.addEventListener('click', () => {
      const t = document.getElementById(tBtn.dataset.collapseTarget);
      if (!t) return;
      const open = t.classList.toggle('is-open');
      tBtn.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
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
        // GRPO group-panel data lives in the slim public sidecar; merge it so the
        // ▲## breakout chip's _tbShowGroup() can resolve. Non-blocking: the board is
        // already rendered. Before a deployment's first pipeline run emits the
        // sidecar, this 404s - an expected outcome, not an error - so mark it
        // unavailable and degrade in the panel.
        fetch(DATA_BASE + "grpo_public.json", { cache: "no-cache" })
          .then(r => r.ok ? r.json() : null)
          .then(g => {
            if (g && g.all_scores && _tbData) { _tbData.all_scores = g.all_scores; _tbGrpoState = "ready"; }
            else { _tbGrpoState = "unavailable"; }
          })
          .catch(() => { _tbGrpoState = "unavailable"; });
        _tbWireFilterToggle();
      })
      .catch(() => {
        const w = document.getElementById("tradeboard-content");
        if (w) w.innerHTML = '<div class="empty-state">This view is temporarily unavailable. Check back shortly.</div>';
      });
  }

  window.TradeMachine = { mount: mount };
})();
