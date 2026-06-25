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
  const bothSides = _TM.a.length && _TM.b.length;
  const posSum = Math.max(0, dA) + Math.max(0, dB);
  const aPct = posSum > 0 ? Math.round(100 * Math.max(0, dA) / posSum) : 50;
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
function _tbSortRows(rows) {
  // null/undefined/"" -> null (NOT 0). Number(null)===0 is finite, which used to make
  // age-less MLB players sort as "age 0" -> 33-yo vets appeared under "Youngest".
  const num = v => (v == null || v === "") ? null : (Number.isFinite(Number(v)) ? Number(v) : null);
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
  if (mm == null) return "–";
  const a = Math.abs(Number(mm));
  const sign = mm < 0 ? "-$" : "$";   // surplus can be negative (overpaid MLB contracts)
  return a >= 100 ? `${sign}${a.toFixed(0)}M` : `${sign}${a.toFixed(1)}M`;
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
  <table class="stats-table tm-board-table">
  <thead><tr>
    <th>#</th>
    <th>Player</th>
    <th class="tm-num" title="Current age (decimal years)">Age</th>
    <th>Pos</th>
    <th>Org</th>
    <th class="tm-num" title="Future Value grade (prospects only - hidden for MLB players where FV is no longer relevant)">FV</th>
    <th class="tm-num tm-col-div" title="Surplus value ($M of production above cost) - the same value_framework model PROSPX and MLB Projections use">Surplus</th>
    <th title="Contract: phase · salary · free agency year (MLB) or remaining controlled seasons (MiLB)">Contract</th>
    <th class="tm-col-div">Signals</th>
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
    // GRPO breakout badge - a within-cohort breakout SIGNAL (display only; it no longer
    // shifts the surplus, which is now the platform xFV/Projections value). Click -> group.
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
      <td class="tm-player">${name}</td>
      <td class="tm-num tm-dim">${p.age != null ? Number(p.age).toFixed(1) : "–"}</td>
      <td class="tm-dim">${pos}</td>
      <td><span class="tm-org-cell">${org ? _tmTeamLogo(org) : ""}<span class="tm-org-abbr">${org}</span></span></td>
      <td class="tm-num tm-dim">${fv}</td>
      <td class="tm-num tm-col-div tm-surplus" style="color:${tvCol};">${_tbFmt(tv)}</td>
      <td class="tm-contract">${_tbCtrlBadge(p)}</td>
      <td class="tm-col-div tm-signals">${signals}</td>
    </tr>`;
  });
  html += `</tbody></table>${topPager}`;
  wrap.innerHTML = html;
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
      .then(d => { _tbData = d; window._tbData = d; _tbPopulateSelectFilters(); _renderTBRows(); _tbWireFilters(); })
      .catch(e => {
        wrap.innerHTML = `<div class="empty-state">Trade Board data not found (<code>data/trade_values.json</code>). Run <code>python run_monthly.py --rebuild-only</code> to generate it.<br><small>${e}</small></div>`;
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
