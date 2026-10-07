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
// Surplus $M -> board tier. The SAME cuts the board's tier filter and the
// server's bayes_trade_value._platform_tier use (Elite $40M+ / High $20-40M /
// Mid $8-20M), so one dollar figure gets one tier everywhere.
function _tmTierOf(mm) {
  const v = Number(mm);
  if (!isFinite(v)) return "low";
  if (v >= 40) return "elite";
  if (v >= 20) return "high";
  if (v >= 8)  return "mid";
  if (v >= 0)  return "low";
  return "minimal";
}
// BOARD AND EVALUATOR COLOUR. Both columns are painted from the VALUE, on the
// value ruler's `trade` ladder (100 / 40 / 15 / 8 / 3 $M plus a red step under
// zero), so the Surplus figure and the letter Grade beside it can never
// disagree: the ladder IS the grade ladder merged to seven tiers, so every
// letter falls in exactly one tier and the map is monotone by construction
// (A+ elite, A/A- great, B+/B good, B- above, C avg, D below, F poor).
// _tmTierOf is deliberately NOT the colour source: it is shared with the
// board's tier FILTER and mirrors bayes_trade_value._platform_tier, and colour
// must never ride the function the filter and the server share.
// Measured on trade_values.json (n = 6,426): page 1 of the board goes from 100%
// one colour to 48.0 / 52.0, the top 250 to 9.6 / 29.6 / 60.8.
function _tbValTier(mm) { return EephusTiers.varOf(mm, "trade"); }
// Evaluator value color. It used to break at 80/35/12 against the board's
// 40/20/8, so an $18M asset read plain grey in the evaluator and cyan "mid" one
// tab over on the board, on the same number from the same file. Both surfaces
// call the SAME ladder now, so that class of drift is closed by construction.
// A negative surplus is a liability and the ruler's red step says so, which is
// the only tier a negative can land in.
function _tmValColor(mm) { return _tbValTier(mm) || "var(--text-secondary)"; }
// FV display rule, ONE implementation for the board's FV column and the
// evaluator's search / seed sub-lines: the eFV grade LEADS and rounds to
// NEAREST, the consensus FV is the fallback and rounds UP (the platform's
// grade-rounding rule). The sub-lines used to print the raw consensus close -
// "FV 52.5" - which is neither rounded nor the grade the board ranks on, so the
// same prospect read 52.5 in search and 53 in the column beside it.
function _tmFvNum(xfvGrade, consensusFv) {
  const x = Number(xfvGrade);
  if (xfvGrade != null && isFinite(x)) return String(Math.round(x));
  const c = Number(consensusFv);
  if (consensusFv != null && isFinite(c)) return String(Math.ceil(c));
  return "";
}
// The same number, labelled with the basis it came from. The board column has a
// header saying "FV" and no room; a sub-line has room to be exact.
function _tmFvText(xfvGrade, consensusFv) {
  const n = _tmFvNum(xfvGrade, consensusFv);
  if (!n) return "";
  return ((xfvGrade != null && isFinite(Number(xfvGrade))) ? "eFV " : "FV ") + n;
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

// What acquiring this player is worth, in raw dollars. `surTotal` (2026-08-03)
// is the balance of the season in progress plus the NPV of every controlled
// season after it; `surNpv` covered only the seasons from 2027 on, which priced
// a deadline rental at nothing and made every expiring contract read as having
// no trade value at all. The fallback keeps a pre-2026-08-03 artifact readable.
function _tmProjValue(proj) {
  if (!proj) return null;
  if (proj.surTotal != null) return proj.surTotal;
  if (proj.surNpv != null) return proj.surNpv;
  return null;
}

// Name the basis so the row does not claim more than it knows. A player whose
// only priced months are the rest of this season is a rental, and saying so is
// the difference between an honest small number and a number that looks broken.
function _tmValueLabel(proj) {
  if (proj && proj.surNpv == null && proj.surRos != null) return "rest-of-season control";
  if (proj && proj.surRos != null) return "contract surplus, incl. rest of season";
  return "contract surplus";
}

// The rental leg, in $M. `surRos` is the balance of the season in progress -
// undiscounted, prorated salary already netted out - and it is the reason a
// deadline vet is priceable at all. It drove a label string and nothing else, so
// the split between "what he is worth for the stretch run" and "what he is worth
// after it" was carried in the artifact and shown nowhere. Note the unit break in
// the projection payload: surTotal / surNpv are raw dollars, surRos is $M.
function _tmRosMm(proj) {
  return (proj && proj.surRos != null && isFinite(Number(proj.surRos)))
    ? Number(proj.surRos) : null;
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
      sub: [p.position || "", p.org || "", _tmFvText(p.xfv_grade, p.fv_close)].filter(Boolean).join(" · "),
      mm: sv }); _TM.seeded = true; }
  } else if (kind === "mlb") {
    if (!_TM.detail) return;                 // detail still loading; seed on the re-render
    const d = _TM.detail[key];
    const pv = d ? _tmProjValue(d.proj) : null;
    if (pv != null) {
      _TM.a.push({ kind: "mlb", key, name: d.name, pos: d.pos || "", org: d.team || "",
        sub: `${d.pos || ""} · ${d.team || "FA"} · ${_tmValueLabel(d.proj)}`, mm: pv / 1e6,
        ros: _tmRosMm(d.proj) });
    } else {
      const b = (DATA.mlbBoard || []).find(x => x.player_key === key);
      if (b) _TM.a.push({ kind: "mlb", key, name: b.player_name, pos: b.position || "",
        org: b.org || "", sub: `${b.position || ""} · ${b.org || ""} · board value`, mm: b.mm });
    }
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
        sub: [p.position || "", p.org || "",
              _tmFvText(p.xfv_grade, p.fv_close)].filter(Boolean).join(" · "),
        mm: sv });
    }
  }
  if (_TM.detail) {
    for (const k in _TM.detail) {
      if (out.length >= 10) break;
      const d = _TM.detail[k];
      const pv = _tmProjValue(d.proj);
      if ((d.name || "").toLowerCase().includes(q) && pv != null) {
        out.push({ kind: "mlb", key: k, name: d.name,
          org: d.team || "", pos: d.pos || "",
          sub: `${d.pos || ""} · ${d.team || "FA"} · ${_tmValueLabel(d.proj)}`,
          mm: pv / 1e6, ros: _tmRosMm(d.proj) });
      }
    }
  }
  // Board-valued MLB players whose detail row carries no projection surplus.
  // Without this they are priced on the board and findable nowhere.
  const seen = new Set(out.map(o => o.key));
  for (const p of (DATA.mlbBoard || [])) {
    if (out.length >= 12) break;
    if (seen.has(p.player_key)) continue;
    if (!(p.player_name || "").toLowerCase().includes(q)) continue;
    out.push({ kind: "mlb", key: p.player_key, name: p.player_name,
      org: p.org || "", pos: p.position || "",
      sub: `${p.position || ""} · ${p.org || ""} · board value`,
      mm: p.mm });
  }
  // Players we MODEL but cannot price, surfaced as unselectable rows carrying
  // the reason. Returning nothing for a real major-leaguer reads as "the site
  // has never heard of him"; it is why someone went looking for A.J. Minter in
  // the source. They are disabled because there is no value to trade, not
  // because we are hiding them.
  for (const u of (_TM.unpriced || [])) {
    if (out.length >= 12) break;
    if (!(u.name || "").toLowerCase().includes(q)) continue;
    if (out.some(o => o.key === u.key)) continue;
    out.push({
      kind: "unpriced", key: u.key, name: u.name,
      org: u.org || "", pos: u.pos || "", mm: null,
      disabled: true,
      // "no controlled season to trade" was false at the deadline: the club
      // controls him for the rest of the season, and since 2026-08-03 that is
      // priced. A row only lands here now when there is no salary on file to
      // price the remainder with, so say that instead.
      sub: u.reason === "expiring"
        ? `${u.pos || ""} · ${u.org || "FA"} · contract ends ${u.thru}; no salary on file for the remainder`
        : `${u.pos || ""} · ${u.org || "FA"} · no contract on file; surplus not priced`,
    });
  }
  return out;
}

function _tmTotal(side) {
  return side.reduce((s, x) => s + (x.mm || 0), 0);
}

// ---- CBT context (owner answer M27-4, 2026-09-25) -------------------------
// Display only: one block per side with the club's CBT position before and
// after the trade, for the 2026 prorated remainder and for 2027, read from the
// Club Ledger's CBT slice (the trade_cbt sidecar ledger_export writes). No
// figure here enters a trade value or the verdict above it. The functions
// between this marker and the end marker are pure; the tests run them in a
// real JS engine on fixtures.

// The 2022 CBA schedule, the same arithmetic as ledger_export.computed_cbt_bill:
// base rate by payor year on the first tier, plus each surcharge above it.
function _tmCbtBaseKey(tier) {
  const t = String(tier || "Non-Tax").trim();
  if (t.startsWith("2nd")) return "2";
  if (t.startsWith("3")) return "3+";
  return "1";
}
function _tmCbtBill(tax, threshold, tier, rates, tiers) {
  if (tax == null || threshold == null || !rates || !tiers) return { over: null, bill: null, bracket: null };
  const over = Number(tax) - Number(threshold);
  const t1 = Number(tiers[0]), t2 = Number(tiers[1]), t3 = Number(tiers[2]);
  const k = _tmCbtBaseKey(tier);
  const base = Number(rates.base_rate_by_payor_year[k]);
  const sur = rates.surcharge_rates;
  const s1 = Number(sur.tier1);
  const s2 = Number(k === "1" ? sur.tier2_first : sur.tier2_repeat);
  const s3 = Number(sur.tier3);
  if (over <= 0) return { over: over, bill: 0, bracket: "under" };
  const clip = (x, lo, hi) => Math.max(lo, Math.min(hi, x));
  const bill = base * Math.min(over, t1)
    + (base + s1) * clip(over - t1, 0, t2 - t1)
    + (base + s2) * clip(over - t2, 0, t3 - t2)
    + (base + s3) * Math.max(over - t3, 0);
  const bracket = over <= t1 ? "base" : over <= t2 ? "surcharge_1" : over <= t3 ? "surcharge_2" : "surcharge_3";
  return { over: over, bill: bill, bracket: bracket };
}

// Days of the regular season still to play on `todayISO` (today counts, the
// acquiring club carries a player from the day he arrives) and the season's
// length, both ends counted. Before Opening Day the whole season is left;
// after the final regular-season day none is.
function _tmCbtDaysLeft(cal, todayISO) {
  if (!cal || !cal.start || !cal.end || !todayISO) return null;
  const day = s => Date.UTC(+s.slice(0, 4), +s.slice(5, 7) - 1, +s.slice(8, 10)) / 86400000;
  const len = day(cal.end) - day(cal.start) + 1;
  const t = day(todayISO);
  const left = t < day(cal.start) ? len : Math.max(0, day(cal.end) - t + 1);
  return { left: left, len: len };
}

// The CBT charge one traded asset carries in `season`, in dollars. Prospects
// carry none here (a 40-man minor leaguer's small charge is not on file). An
// MLB player carries his contract AAV in a season his contract covers. For the
// next season only a signed, guaranteed year counts: the Ledger's next-season
// tax payroll (Spotrac) holds no projected arbitration or pre-arbitration
// salary and no club or mutual option year, so neither does the move.
// known=false means no salary is on file and the asset counts as $0.
function _tmCbtCharge(item, proj, season, seasonNow) {
  if (!item || item.kind === "prospect") return { usd: 0, known: true };
  if (!proj) return { usd: 0, known: false };
  const aav = proj.aav != null && isFinite(Number(proj.aav)) ? Number(proj.aav) : null;
  if (season === seasonNow) {
    if (aav != null && proj.thru != null && Number(proj.thru) >= season) return { usd: aav, known: true };
    return { usd: 0, known: false };
  }
  const row = (proj.salPath || []).find(r => r && Number(r[0]) === season);
  if (!row) return { usd: 0, known: true };              // no season left to carry
  const opt = (proj.salOpt || []).find(o => o && Number(o[0]) === season);
  const optional = opt && (opt[1] === "club" || opt[1] === "mutual");
  if (row[4] !== "signed" || row[5] !== "contract" || optional) return { usd: 0, known: true };
  return { usd: aav != null ? aav : Number(row[1]) || 0, known: true };
}

// One club's CBT position for one season before and after the trade. `net`
// is the AAV the club takes in minus the AAV it sends out (dollars); in the
// season under way only the share of it for the days still to play counts.
function _tmCbtSeason(blk, net, frac, rates, tiers) {
  if (!blk || blk.tax_payroll_usd == null || blk.threshold_usd == null) return null;
  const before = Number(blk.tax_payroll_usd);
  const moved = net * frac;
  const after = before + moved;
  const b0 = _tmCbtBill(before, blk.threshold_usd, blk.tier, rates, tiers);
  const b1 = _tmCbtBill(after, blk.threshold_usd, blk.tier, rates, tiers);
  return { before: before, after: after, moved: moved, threshold: Number(blk.threshold_usd),
           carry: !!blk.carry_forward, tier: blk.tier || "Non-Tax", tierBasis: blk.tier_basis || "",
           bracketBefore: b0.bracket, bracketAfter: b1.bracket,
           marginal: (b1.bill != null && b0.bill != null) ? b1.bill - b0.bill : null };
}

// A side's club is the club that SENDS the players the other side receives
// (the Trade Machine's "receives" framing). One club or none: players from
// two clubs on the far side name no single club.
function _tmCbtClubOf(items, canon) {
  const codes = new Set();
  for (const x of items || []) {
    const c = canon(x && x.org);
    if (c) codes.add(c);
  }
  if (codes.size === 1) return { club: codes.values().next().value };
  return { club: null, why: codes.size > 1 ? "mixed" : "none" };
}

// Everything one side's block prints, as data. `inItems` the side receives,
// `outItems` it sends; `projOf(item)` returns the player's projection block.
function _tmCbtSide(club, inItems, outItems, projOf, cbt, todayISO) {
  const sNow = Number(cbt.season_now), sNext = Number(cbt.class_year);
  const blocks = (cbt.clubs || {})[club];
  if (!blocks) return null;
  const sum = (items, season) => {
    let usd = 0, unknown = 0;
    for (const x of items || []) {
      const ch = _tmCbtCharge(x, projOf(x), season, sNow);
      usd += ch.usd;
      if (!ch.known) unknown += 1;
    }
    return { usd: usd, unknown: unknown };
  };
  const out = { club: club, seasons: [] };
  const cal = (cbt.calendar || {})[String(sNow)];
  const dl = _tmCbtDaysLeft(cal, todayISO);
  const iN = sum(inItems, sNow), oN = sum(outItems, sNow);
  if (dl && dl.left === 0) {
    out.seasons.push({ season: sNow, closed: true });
  } else {
    const r = dl ? _tmCbtSeason(blocks[String(sNow)], iN.usd - oN.usd, dl.left / dl.len, cbt.rates, cbt.surcharge_tiers_usd) : null;
    out.seasons.push(Object.assign({ season: sNow, closed: false, prorated: true,
      daysLeft: dl ? dl.left : null, days: dl ? dl.len : null, noCalendar: !dl,
      unknown: iN.unknown + oN.unknown }, r || {}));
  }
  const iX = sum(inItems, sNext), oX = sum(outItems, sNext);
  const r2 = _tmCbtSeason(blocks[String(sNext)], iX.usd - oX.usd, 1, cbt.rates, cbt.surcharge_tiers_usd);
  out.seasons.push(Object.assign({ season: sNext, closed: false, prorated: false,
    unknown: iX.unknown + oX.unknown }, r2 || {}));
  return out;
}

function _tmUsdM(usd, signed) {
  if (usd == null || !isFinite(Number(usd))) return "-";
  const v = Number(usd) / 1e6;
  const s = Math.abs(v).toFixed(1);   // payrolls near $244M need the decimal
  if (signed) return (v < 0 ? "-$" : "+$") + s + "M";
  return (v < 0 ? "-$" : "$") + s + "M";
}

// The printed lines of one side's block, plain text, so the wording is tested
// exactly as served.
function _tmCbtLines(side, cbt) {
  const br = cbt.brackets || {};
  const bName = k => br[k] || k || "-";
  const basis = cbt.payor_basis || {};
  const lines = [];
  for (const s of side.seasons) {
    if (s.closed) {
      lines.push({ season: s.season, text: `${s.season} closed: the trade does not change ${s.season} tax payroll` });
      continue;
    }
    if (s.before == null) {
      lines.push({ season: s.season, text: s.noCalendar
        ? `${s.season}: the regular-season dates are not on file, so the prorated remainder is not computed`
        : `${s.season}: no tax payroll on file for this club` });
      continue;
    }
    const bits = [];
    bits.push(`tax payroll ${_tmUsdM(s.before)} to ${_tmUsdM(s.after)}`);
    if (s.prorated) bits.push(`${s.daysLeft} of ${s.days} regular-season days left`);
    bits.push(s.carry
      ? `threshold ${_tmUsdM(s.threshold)}, the ${cbt.season_now} figure carried forward (no ${s.season} threshold is published)`
      : `threshold ${_tmUsdM(s.threshold)}`);
    bits.push(s.bracketBefore === s.bracketAfter
      ? `bracket: ${bName(s.bracketBefore)}`
      : `bracket: ${bName(s.bracketBefore)} to ${bName(s.bracketAfter)}`);
    const what = s.prorated ? "prorated AAV moved" : "AAV moved";
    bits.push(`marginal tax ${_tmUsdM(s.marginal, true)} on ${_tmUsdM(Math.abs(s.moved))} of ${what} ${s.moved < 0 ? "out" : "in"} (net)`);
    bits.push(`payor tier ${s.tier}${basis[s.tierBasis] ? ` (${basis[s.tierBasis]})` : ""}`);
    if (s.unknown) bits.push(`${s.unknown} player${s.unknown === 1 ? "" : "s"} with no ${s.season} salary on file count as $0`);
    const head = s.prorated ? `${s.season}, prorated remainder` : `${s.season}`;
    lines.push({ season: s.season, text: `${head}: ${bits.join("; ")}` });
  }
  return lines;
}
// ---- end CBT context ------------------------------------------------------

function _tmTodayISO() {
  const d = new Date();
  const p = n => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

function _tmCanonOrg(org) {
  const hub = window.EEPHUS_HUB;
  const c = hub && hub.club ? hub.club(org) : null;
  return c ? c.code : null;
}

// The CBT block under the verdict. Nothing renders until the slice has
// loaded; a side whose club cannot be named says why instead of guessing.
function _tmCbtHtml() {
  const cbt = _TM.cbt;
  if (!cbt || !cbt.clubs || !(_TM.a.length || _TM.b.length)) return "";
  const projOf = x => (x && x.kind === "mlb" && _TM.detail && _TM.detail[x.key]) ? _TM.detail[x.key].proj : null;
  const today = _tmTodayISO();
  const sideBlock = (label, inItems, outItems, otherLabel) => {
    const who = _tmCbtClubOf(outItems, _tmCanonOrg);
    if (!who.club) {
      const why = who.why === "mixed"
        ? `the players Side ${otherLabel} receives come from more than one club`
        : `Side ${otherLabel} receives no player yet`;
      return `<div class="tm-cbt-side"><div class="tm-cbt-club">Side ${label}</div>
        <div class="tm-cbt-line tm-cbt-dim">Club not named: ${escapeHtml(why)}. A side's club is the one that sends the players the other side receives.</div></div>`;
    }
    const side = _tmCbtSide(who.club, inItems, outItems, projOf, cbt, today);
    if (!side) return "";
    const lines = _tmCbtLines(side, cbt).map(l =>
      `<div class="tm-cbt-line">${escapeHtml(l.text)}</div>`).join("");
    return `<div class="tm-cbt-side"><div class="tm-cbt-club">${_tmTeamLogo(who.club)} Side ${label}: ${escapeHtml(who.club)}</div>${lines}</div>`;
  };
  const src = cbt.source || {};
  const srcBits = [src.payroll, src.thresholds, src.calendar].filter(Boolean).map(escapeHtml).join("; ");
  return `<div class="tm-cbt">
    <div class="tm-cbt-head">${_tmGl("CBT", "cbt_payroll")} context <span class="tm-cbt-dim">display only; the trade values and verdict above do not use it</span></div>
    <div class="tm-cbt-grid">${sideBlock("A", _TM.a, _TM.b, "B")}${sideBlock("B", _TM.b, _TM.a, "A")}</div>
    <div class="tm-cbt-foot">Sources: ${srcBits}. Marginal tax is the change in the computed bill at the club's payor tier, the same schedule the <a href="/ledger/">Club Ledger</a> prints.</div>
  </div>`;
}

// One shared dead-band for "even" trade verdicts, used by BOTH the Trade
// Machine and the Transactions Trade Audit so the two never disagree on what
// counts as balanced. The wider $5M band is deliberate: surplus dollars carry
// real model uncertainty, so a sub-$5M edge is not a meaningful "winner."
const BALANCED_THRESHOLD_MM = 5;

// One-subject card exports go through EEPHUS_HUB.openCard (the shared wrapper -
// DE-DUP 2026-07-23; it prefers the GFX modal, falls back to the direct
// shareCard download).

function renderTradeMachine() {
  const el = document.getElementById("trade-machine");
  if (!el) return;
  _tmEnsureDetail();
  _tmSeedFromURL();
  const sideHtml = (side, label) => {
    const list = _TM[side].map((x, i) => {
      const g = _tbGrade(x.mm), gc = _tbValTier(x.mm);   // contract-adjusted surplus -> letter
      // Rental split, shown rather than merely labelled: how much of this
      // player's price is the balance of the season in progress, and therefore
      // how much of it a buyer keeps past October.
      const rest = (x.ros != null && x.mm != null) ? (x.mm - x.ros) : null;
      // NO FLOOR (owner decision, 2026-08-05). The leg is f * (V(full-season
      // WAR) - full-season salary), so it goes negative whenever the salary
      // still owed outruns the projected production. That is information, not a
      // defect, and the reader who is looking straight at the negative number is
      // the one who needs it said, so the convention rides the chip's own tip.
      const rosNeg = x.ros != null && Number(x.ros) < 0
        ? " Negative is not floored: the salary still owed exceeds the projected production."
        : "";
      const rosChip = x.ros == null ? "" :
        `<span class="tm-sub" title="Rest-of-season control ${_tbFmt(x.ros)} of ${_tbFmt(x.mm)}${rest != null ? `; ${_tbFmt(rest)} in controlled seasons after it` : ""}. Undiscounted, prorated salary netted out.${rosNeg}">rental ${_tbFmt(x.ros)}</span>`;
      return `
      <div class="tm-row">
        <span class="tm-kind tm-kind--${x.kind}" title="${x.kind === "prospect" ? "Prospect (eFV surplus)" : "MLB (contract surplus)"}">${x.kind === "prospect" ? "P" : "M"}</span>
        ${_tmTeamLogo(x.org)}
        <a class="fa-player-link tm-name" href="${x.kind === "prospect" ? `/prospx/#player=${encodeURIComponent(x.key)}` : `/projections/#player=${encodeURIComponent(x.key)}`}">${escapeHtml(x.name)}</a>
        <span class="tm-sub">${escapeHtml(x.pos || "")}</span>
        ${rosChip}
        ${g ? `<span class="tm-grade-chip" style="color:${gc};border-color:${gc};" title="Trade Value Grade ${g} (contract-adjusted surplus)">${g}</span>` : ""}
        <span class="tm-val" style="color:${_tmValColor(x.mm)};">${(x.mm || 0) >= 0 ? "$" : "-$"}${Math.abs(x.mm || 0).toFixed(1)}M</span>
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
  // The verdict DESCRIBES the gap; it does not predict what a club does (QCLC02,
  // 2026-10-07). The old grader printed "may hesitate" (15-40% gap), "likely
  // rejects" (40-70%) and "won't do this" (70%+), tiers with no receipt: the
  // registry row trade_machine_surplus is provisional with no win claims and
  // its eval artifact does not ship. The $5M balanced band is the
  // one rule the glossary documents, and it stays. In the "receives" framing
  // the side that RECEIVES less value is the one named.
  let vClass = "", vText = "";
  if (!bothSides) { vText = "Add players to both sides for a verdict."; }
  else if (diff < BALANCED_THRESHOLD_MM) { vText = `Balanced: within $${BALANCED_THRESHOLD_MM}M.`; vClass = "is-bal"; }
  else { vText = `Side ${behind} receives $${diff.toFixed(1)}M less (${pct.toFixed(0)}% gap).`; }
  const verdict = have
    ? `<div class="tm-verdict">
         <div class="tm-balbar" title="value split A vs B">
           <div class="tm-balbar-a" style="width:${aPct}%"></div>
           <div class="tm-balbar-b" style="width:${100 - aPct}%"></div>
         </div>
         <div class="tm-balrow">
           <span class="tm-balverdict ${vClass}">${vText}</span>
           <span class="fa-sub"><span data-gl="surplus_value">surplus</span>: prospect surplus NPV + MLB club control window surplus (guaranteed seasons in full, unsigned seasons through the fifth projected season) · $${BALANCED_THRESHOLD_MM}M dead-band</span>
         </div>
         <div class="tm-controls">
           <button class="chip" data-tm-clear type="button">Clear</button>
           <button class="chip" data-tm-copy type="button">Copy as text</button>
           ${bothSides ? `<button class="chip" data-tm-gfx type="button" title="Shareable deal graphic">Generate GFX</button>` : ""}
         </div>
       </div>`
    : "";
  el.innerHTML = `<div class="tm-wrap">
    <div class="detail-title" style="font-size:13px;"><span data-gl="trade_machine">Trade Machine</span></div>
    <div class="tm-grid">${sideHtml("a", "Side A")}${sideHtml("b", "Side B")}</div>
    ${verdict}
    ${_tmCbtHtml()}
  </div>`;
  _tmWireGl(el);
  el.querySelectorAll("[data-tm-search]").forEach(inp => {
    inp.oninput = () => {
      const side = inp.dataset.tmSearch;
      const res = el.querySelector(`[data-tm-results="${side}"]`);
      const hits = _tmSearch(inp.value);
      res.innerHTML = hits.map((h, i) => h.disabled
        ? `<button class="tm-hit is-unpriced" type="button" disabled
             title="Projected, but no contract surplus to trade">
             <strong>${escapeHtml(h.name)}</strong> <span class="tm-sub">${escapeHtml(h.sub)}</span>
             <span class="tm-val">not tradeable</span></button>`
        : `<button class="tm-hit" data-tm-add="${side}:${i}" type="button">
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
      ` ${x.name} (${[x.pos, x.org].filter(Boolean).join(", ")}${x.org || x.pos ? ", " : ""}${x.kind === "prospect" ? "prospect" : "MLB"}) ${(x.mm || 0) >= 0 ? "$" : "-$"}${Math.abs(x.mm || 0).toFixed(1)}M`
    ).join("\n");
    const text = `=== Trade Machine (eephus.io) ===\n\nSide A receives:\n${fmt("a") || "  (none)"}\n  Total: $${dA.toFixed(1)}M\n\nSide B receives:\n${fmt("b") || "  (none)"}\n  Total: $${dB.toFixed(1)}M\n\nGap: $${Math.abs(dA - dB).toFixed(1)}M`;
    const done = () => { copyB.textContent = "Copied!"; setTimeout(() => { copyB.textContent = "Copy as text"; }, 1300); };
    if (navigator.clipboard) navigator.clipboard.writeText(text).then(done, () => prompt("Copy this trade:", text));
    else prompt("Copy this trade:", text);
  };
  // Shareable deal card (only wired when both sides carry an asset).
  // Declarative since GFX slice 4: the "deal" template owns the layout (four
  // totals/gap/verdict tiles + one "receives" section per side); this site
  // only supplies each asset's data. Each asset row carries its Trade Value
  // Grade letter (the same _tbGrade the live UI chips show).
  const gfxB = el.querySelector("[data-tm-gfx]");
  if (gfxB) gfxB.onclick = () => {
    const asset = x => ({
      name: x.name,
      grade: _tbGrade(x.mm),
      value: `${x.mm >= 0 ? "$" : "-$"}${Math.abs(x.mm || 0).toFixed(1)}M`,
      neg: !((x.mm || 0) >= 0),
    });
    // Descriptive, like the line it captions: balanced, or which side
    // receives more and by what share of the larger side.
    const vWord = vClass === "is-bal" ? "Balanced" : `Side ${lead} +${pct.toFixed(0)}%`;
    window.EEPHUS_HUB.openCard({
      template: "deal",
      data: {
        sideA: { total: `$${dA.toFixed(1)}M`, assets: _TM.a.map(asset) },
        sideB: { total: `$${dB.toFixed(1)}M`, assets: _TM.b.map(asset) },
        gap: `$${diff.toFixed(1)}M`,
        verdict: vWord,
      },
      module: "Trade Machine",
      accentToken: "--accent-cyan",
      name: "Trade Evaluation",
      meta: "one currency · prospect eFV surplus + MLB contract surplus",
      sub: `verdict: ${vWord.toUpperCase()}`,
      url: "eephus.io/trademachine",
      filename: "eephus-trademachine-deal.png",
      caption: vText,
    });
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
// The registry's word for the GRPO breakout model (row grpo_prospect), printed
// on the breakout chip. The audit of 2026-10-02 (QCLC05) caught the chip
// saying "provisional" while the row said "unvalidated"; the 30-day forward
// read moved the row to provisional the same day. A test pins this constant
// to the registry row so the two cannot drift again.
const _TB_GRPO_VERDICT = "provisional";
let _tbPool   = "all";
let _tbTier   = "all";
let _tbPos    = "all";
let _tbOrg    = "all";
let _tbExactPos = "all";
// null = the pool default (_tbEffSort). Set only when the reader picks a sort.
let _tbSort   = null;
let _tbQ      = "";        // free-text search
// Full filtered+sorted board array from the latest _renderTBRows, captured so
// the Generate GFX board spec renders the exact on-screen ordering (the modal
// caps to the chosen Show count itself).
let _tbLastRows = [];

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
// DELETED 2026-09-16: the board's tier-to-colour map. Five colours keyed on the
// tier NAME, one of which (--card-gold) was not a defined token, so the top
// tier's colour was the empty string in both themes. The board colours from the
// value now.
function _tbIsMlb(p) {
  return p && (p.status === "graduated" || p.status === "debuted");
}
// Where a board row goes when clicked. A row carries `proj_key` only when its
// own player_key names a DIFFERENT human (or nobody) on /projections/: the ATH
// infielder Max Muncy holds the slug max_muncy on the board while
// /projections/#player=max_muncy is the LAD veteran. proj_key null means the
// projection system does not model this human, so an MLB row falls back to
// his PROSPX page instead of opening someone else's.
function _tbNavTarget(p, isMlb) {
  if (!p || !p.player_key) return null;
  if (!isMlb) return { key: p.player_key, mlb: false };
  if (!("proj_key" in p)) return { key: p.player_key, mlb: true };
  return p.proj_key ? { key: p.proj_key, mlb: true } : { key: p.player_key, mlb: false };
}
function _tbPrimaryPos(pos) {
  const s = String(pos || "").toUpperCase().trim();
  if (!s) return "";
  const parts = s.split("/").map(x => x.trim()).filter(Boolean);
  const order = ["C","SS","CF","2B","3B","1B","LF","RF","OF","SP","RP","CL","RHP","LHP","P","DH"];
  return order.find(x => parts.includes(x)) || parts[0] || "";
}
// The board's default order is SURPLUS, the value the board prints, colours and
// grades (M08-03, 2026-09-25). The MiLB pool defaults to the eFV grade, and the
// "eFV grade" option orders prospects only.
//
// UNTIL 2026-09-25 THE DEFAULT WAS THE RAW eFV GRADE ON EVERY ROW. For a debuted
// player that is the grade frozen at his last pre-debut snapshot, which the FV
// column does not print for MLB rows, so the order had no visible key: Carlos
// Correa (minus $60.7M, F) sat sixth, Kris Bryant and Xander Bogaerts 13th and
// 14th, and the largest surplus on the board ranked 185th. The eval that was
// cited for it (data/trade_machine_eval.json slice_a) scores prospects against
// career WAR; nothing in it scores the grade as an order for veteran contracts,
// and the registry row for the board says the headline sort is the surplus.
//
// "trade_desc" is the LEGACY value of the eFV grade option and still maps to
// the grade column, so a bookmarked or remembered selection resolves.
function _tbEffSort() {
  if (_tbSort) return _tbSort;
  return _tbPool === "milb" ? "trade_desc" : "surplus_desc";
}
// Parse the effective sort string into [column, direction].
function _tbSortParts() {
  const s = _tbEffSort();
  if (s === "trade_desc") return ["grade", "desc"];
  const i = s.lastIndexOf("_");
  if (i < 0) return [s, "desc"];
  return [s.slice(0, i), s.slice(i + 1)];
}
// Keep the Sort control naming the ordering the board is showing.
function _tbSyncSortSelect() {
  const sel = document.getElementById("tb-sort-select");
  if (!sel) return;
  const eff = _tbEffSort();
  const opt = (eff === "grade_desc") ? "trade_desc" : eff;
  sel.value = opt;
  if (sel.value !== opt) sel.selectedIndex = -1;
}
// Per-column accessor (numeric -> null when absent so nulls always sort last;
// text -> string). The "grade" key is the raw eFV grade (xfv_grade) and is
// scoped to prospects: an MLB row returns null, so under the eFV grade sort the
// prospects lead in grade order and the MLB rows follow in surplus order.
//
// What data/trade_machine_eval.json measures for the grade as an orderer, on
// prospects against career WAR: pooled 0.3433 against surplus 0.3289 with no
// interval, and by tier (slice_a.by_tier) elite 0.2328 against 0.1490, high
// 0.2485 against 0.1507, mid 0.2536 against 0.0820, low 0.0683 against 0.0816,
// where the grade loses. Low holds 1,301 of the 2,333 scored rows. No page
// copy restates these figures, and the grade does not beat surplus in every tier.
// Note: since the 2026-07-06 quantile flip, surplus
// dollars are priced on the DISPLAYED quantile grade, not this raw grade -
// they are related but distinct orderers. Surplus stays on trade_value_mm.
// The season in progress. The control END the payload carries is an absolute
// year; the colour band and the contract sort both want a SPAN, and this module
// had no season constant of its own.
//
// IT COMES OFF THE PAYLOAD, NOT THE READER'S CLOCK. Every other surface derives
// its seasons from the artifact it was served (DATA.first_season on
// /projections/), and a board whose colour bands and sort order shift at
// midnight on 1 January - or on a machine whose timezone is a day ahead - is
// reporting the reader's calendar, not the regen's. `generated_at` is stamped
// by the same run that stamps `control_thru`, so the two cannot disagree. The
// clock is the fallback for a payload with no stamp at all.
function _tbCurSeason() {
  const m = /^(\d{4})/.exec(String((typeof _tbData !== "undefined" && _tbData && _tbData.generated_at) || ""));
  return m ? Number(m[1]) : new Date().getUTCFullYear();
}

// The contract word for a row the salary path never priced. 860 of 1752 MLB
// rows are in that state (420 pre-arb, 155 arb, 102 team control, 41 on an
// extension, 60 free agents, 81 with nothing on file), and for one revision of
// this change they rendered a bare salary or an empty cell: the control end
// replaced the phase instead of joining it. The phase is translated into the
// site's lexicon rather than printed raw - "Ext. thru 2028" is a GUARANTEED
// contract fact and takes the guarantee word, "Team Control" becomes "Club
// control" with no year because the row has none - and the class words
// (Pre-Arb, Arb) stay, because they describe a SEASON and not a window.
function _tbPhaseWord(phase) {
  const s = String(phase || "").trim();
  if (!s || s === "-") return null;
  const m = /^Ext\. thru (\d{4})$/.exec(s);
  if (m) return `Guar. thru ${m[1]}`;
  return s === "Team Control" ? "Club control" : s;
}

function _tbSortVal(p, col) {
  const num = v => (v == null || v === "") ? null : (Number.isFinite(Number(v)) ? Number(v) : null);
  if (col === "age") return { n: num(p.age) };
  if (col === "fv")  return { n: num(p.fv) };
  if (col === "org") return { t: String(p.org || "") };
  if (col === "pos") return { t: _tbPrimaryPos(p.position) };
  if (col === "name") return { t: String(p.player_name || "") };
  // The Contract column sorts on the last season the club CONTROLS him. It
  // sorted on debut+6 (`remaining_control_years`) while its own tooltip named
  // the salary path's window end, which is two window lengths in one column;
  // 597 of 892 rows change their key. The old field is the fallback for a row
  // the path never priced.
  if (col === "contract") {
    var _ct = num(p.control_thru);
    return { n: _ct != null ? _ct - _tbCurSeason() + 1 : num(p.remaining_control_years) };
  }
  if (col === "risk") return { n: num(p.sortino) };   // downside-adjusted surplus
  if (col === "surplus") return { n: num(p.trade_value_mm) };   // explicit $ column
  return { n: _tbIsMlb(p) ? null : num(p.xfv_grade) };   // grade - eFV grade orderer, prospects only
}
function _tbSortRows(rows) {
  const [col, dir] = _tbSortParts();
  const sign = dir === "asc" ? 1 : -1;
  const tv = p => { const v = Number(p.trade_value_mm); return Number.isFinite(v) ? v : -1e9; };
  // Cross-key tiebreaks: surplus $ then the FINEST available eFV orderer. The
  // convex-$/WAR + $0-floor surplus transform bunches a large low/fringe block at
  // one trade_value_mm AND one displayed grade, where xfv_grade can no longer
  // separate rows. xfv_war_6yr is the continuous WAR projection behind the grade,
  // so it breaks those $-floor ties finer; fall back to xfv_grade when it's
  // absent (older exports). Display value stays trade_value_mm.
  const xw = p => { const v = Number(p.xfv_war_6yr); return Number.isFinite(v) ? v : null; };
  const xg = p => { const v = Number(p.xfv_grade); return Number.isFinite(v) ? v : -1e9; };
  const efvTie = (a, b) => {                      // war6 desc when both present, else grade desc
    const aw = xw(a), bw = xw(b);
    if (aw != null && bw != null && aw !== bw) return bw - aw;
    return xg(b) - xg(a);
  };
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
    return c || (tv(b) - tv(a)) || efvTie(a, b);   // surplus desc, then finest eFV orderer
  });
  return rows;
}
// Render a clickable, sort-aware column header with an active-direction arrow.
// GLOSSARY TERM SPAN (assets/eephus-gl.js contract: a [data-gl] span carrying a
// slug that EXISTS in data/glossary.json, plus one wire() call after render).
// Slugs are verified against the artifact before use, because a span pointing
// at a slug the artifact does not carry renders a term that looks interactive
// and defines nothing.
//
// WHAT IS DELIBERATELY NOT WRAPPED HERE: "posterior" (as in the evaluator's
// posterior_surplus_mm) and "Trade Value Grade" have no entry in
// data/glossary.json. They stay plain text rather than borrowing a near-miss
// slug; add the entries in build_glossary_data.py and the spans can follow.
function _tmGl(label, slug) {
  return `<span class="g-term" data-gl="${slug}">${label}</span>`;
}
function _tmWireGl(node) {
  try { if (node && window.EEPHUS_GL && EEPHUS_GL.wire) EEPHUS_GL.wire(node); }
  catch (e) { /* the glossary is enrichment; the board works without it */ }
}
// `term` is optional: with it the heading text becomes a glossary span, without
// it the label renders exactly as before.
function _tbTh(label, col, cls, title, noActiveMark, term) {
  const [scol, sdir] = _tbSortParts();
  const active = !noActiveMark && scol === col;
  const arrow = active ? (sdir === "asc" ? " ▲" : " ▼") : "";
  const classes = ["tm-sortable", cls, active ? "tm-sorted" : ""].filter(Boolean).join(" ");
  const tt = (title ? title + " · " : "") + "click to sort";
  const ariaSort = active ? (sdir === "asc" ? "ascending" : "descending") : "none";
  const text = term ? _tmGl(label, term) : label;
  return `<th class="${classes}" data-tb-sortcol="${col}" title="${tt}" scope="col" tabindex="0" aria-sort="${ariaSort}">${text}${arrow}</th>`;
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
  // THE DROPDOWN MUST NAME THE ORDERING IT IS SHOWING. This used to snap BOTH
  // grade_desc and surplus_desc back to the single "trade_desc" option, so
  // clicking the Surplus header left the control reading the grade option and a
  // reader had no way to tell the two orderings apart. Only the grade sort
  // aliases now; surplus is its own option and selects itself.
  _tbSyncSortSelect();
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
  const col = w.score > 0.5 ? "var(--neon-red)" : "var(--text-amber)";
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
  // text takes the amber READING ink (the neon read 2.13:1 on light paper); the border keeps the neon
  const col = sc >= 55 ? "var(--neon-red)" : sc >= 30 ? "var(--text-amber)" : "var(--text-secondary)";
  const bord = sc >= 55 ? "var(--neon-red)" : sc >= 30 ? "var(--neon-amber)" : "var(--text-secondary)";
  const tip = `Roster crunch ${sc}: ${c.rule5_exposed ? "Rule 5 exposed this November; " : ""}`
    + `${c.on_40_man ? "on the 40-man" : "off the 40-man"} · ${c.options_left} option${c.options_left === 1 ? "" : "s"} left`
    + `${c.service_phase && c.service_phase !== "none" ? " · " + escapeHtml(c.service_phase) : ""}`;
  return ` <span class="chip" style="padding:1px 5px;font-size:9px;color:${col};border-color:${bord};" title="${tip}">${bits.join(" ")}</span>`;
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
    return `<span style="font-size:10px;color:var(--text-amber);">${escapeHtml([sal, fa].filter(Boolean).join(" · "))}</span>`;
  }

  // MLB player: full contract spec
  const phase = cc.phase || " - ";
  const sal   = cc.current_salary_mm != null
    ? (cc.current_salary_mm < 1 ? `$${(cc.current_salary_mm*1000).toFixed(0)}k` : `$${cc.current_salary_mm.toFixed(1)}M`)
    : null;
  // `fa_year` is NOT read in this branch. It was declared here and never used:
  // `parts` and `tip` are both built without it, so the column header's promise
  // of an FA year was a promise no row could keep. The club control end below
  // is the figure that answers the question it was asked.
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
  // The club's right (owner answer VAL2-Q2): the value beside this row already
  // prices a club option the club would decline at $0, never below.
  const _cDecl = Array.isArray(p.club_option_declined) && p.club_option_declined.length
    ? `Club option ${_fmtYears(p.club_option_declined)} declined on the mean path: priced at $0, never below (the club's right)` : null;

  // ASK C (2026-09-16, decision D4 - the evaluator is one number per player by
  // design, so it gets the BASIS in the tooltip and not the strip). Where the
  // salary path knows the window end, the tooltip states it and the row stops
  // resting on `remaining_control_years` (debut+6), which is still emitted for
  // the rank gate but is no longer the thing a reader is shown.
  const _ctThru = p.control_thru != null ? p.control_thru
    : (p.salary_thru != null ? p.salary_thru : null);
  const _ctOpen = p.control_thru != null ? !!p.control_open : false;
  // A PLAYER OPT-OUT IS A CEILING ON THE WINDOW, NOT A FOOTNOTE TO IT.
  // `control_end` takes max(guarantee, priced path), so a deal with an opt-out
  // inside it reports the last GUARANTEED season as the control end: 2039 for
  // Soto, 2037 for Witt, 2034 for Julio. The right to leave is the player's,
  // and this module is the one that states the window in words, so the words
  // carry the qualifier. The strip already prints `P-opt 2030-33` beside it.
  const _optTail = (cc.player_opt_years && cc.player_opt_years.length)
    ? ` unless he opts out (${_fmtYears(cc.player_opt_years)})` : "";
  const _spThru = _ctThru != null
    ? (_ctOpen ? `Club control through at least ${_ctThru}${_optTail}`
               : `Club control through ${_ctThru}${_optTail}`)
    : (_tbPhaseWord(phase)
        ? `${_tbPhaseWord(phase)} on service time; no salary path prices this row, so no controlled season is named`
        : null);
  const _spBasis = p.salary_basis ? `Salary basis: ${String(p.salary_basis).replace(/_/g, " ")}` : null;
  const _spCut = p.salary_cut_season != null
    ? `Not tendered from ${p.salary_cut_season}: carrying him through the rest of his arbitration years costs more than he is worth` : null;
  const _spBand = Array.isArray(p.surplus_salary_band_mm)
    ? `If the award lands at the band ends: $${p.surplus_salary_band_mm[0]}M to $${p.surplus_salary_band_mm[1]}M` : null;
  const tip = [sal && `Salary: ${sal}/yr`, pOpts, cOpts, _cDecl,
               _spThru, _spBasis, _spBand, _spCut].filter(Boolean).join(" · ");
  // THE YEAR IS ON THE STRIP, not only in the title. A tooltip is unreachable
  // on touch and absent from the CSV, and the strip used to show `cc.phase`
  // alone ("Pre-Arb" / "Arb" / "Team Control" / "Ext. thru YYYY") - derived
  // from debut+6 and carrying no year at all. Where the path knows the end, the
  // end replaces it; where it does not, the phase is still the only thing the
  // row knows and it keeps the cell. The band reads the control end where there
  // is one and the debut+6 proxy where there is not.
  // ONE SPAN EXPRESSION, shared with the column's sort key. The band's
  // thresholds were calibrated on `remaining_control_years`, which COUNTS the
  // season in progress, so dropping the +1 here shifted every row one band
  // darker than the sort that sits beside it.
  const _ctSpan = _ctThru != null ? (_ctThru - _tbCurSeason() + 1) : ctrl;
  const col = _ctSpan >= 5 ? "var(--neon-green)" : _ctSpan >= 2 ? "var(--text-amber)" : "var(--text-secondary)";
  const head = _ctThru != null
    ? `Ctrl thru ${_ctThru}${_ctOpen ? "+" : ""}`
    : _tbPhaseWord(phase);
  const parts = [
    head ? `<span style="font-weight:600;${p.control_est ? "border-bottom:1px dashed currentColor;" : ""}">${escapeHtml(head)}</span>` : "",
    sal  ? `<span style="color:${col}">${sal}</span>` : "",
    pOpts ? `<span style="color:var(--text-amber);font-size:9px;" title="Player can opt out">${escapeHtml(pOpts)}</span>` : "",
    cOpts ? `<span style="color:var(--text-secondary);font-size:9px;" title="Team holds option">${escapeHtml(cOpts)}</span>` : "",
  ].filter(Boolean).join(" · ");

  // 81 MLB rows carry no control end, no phase and no salary. They rendered a
  // " - " placeholder before the Contract column was rebuilt and an EMPTY cell
  // after it, which reads as a rendering failure rather than as "nothing on
  // file"; the site's own idiom for the second is a dash.
  return `<span style="font-size:10px;line-height:1.3;" title="${escapeHtml(tip)}">${parts || " - "}</span>`;
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
// DELETED 2026-09-16: the grade-to-colour map. Nine letters into five colours,
// off the LETTER rather than the number, so the Grade chip and the Surplus
// figure beside it could land on different colours for the same player. Both
// take _tbValTier.

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
  const pb = p.p_bust;
  // NO RATIO IS NOT NO INFORMATION. bayes_trade_value withholds the Sortino when
  // the outcome fan is flat, because the ratio is a constant there and the
  // column reads "higher is safer". This used to bail on a null Sortino and drop
  // the bust chip with it, which threw away the ground-truthed P(bust) on the
  // very rows where it is the only risk number there is: 3,862 of 5,264.
  if (p.sortino == null && pb == null) return `<td class="tm-num tm-dim">-</td>`;
  const col = pb == null ? "var(--text-secondary)"
    : pb >= 0.25 ? "var(--neon-red)" : pb <= 0.10 ? "var(--neon-green)" : "var(--text-primary)";
  const tip = [
    p.sortino != null
      ? `Sortino ${p.sortino}: expected surplus per unit of downside risk (higher is safer)`
      : "No Sortino: the outcome fan is flat here (more than 80% of modelled outcomes land on one figure), so the ratio would be a constant; withheld",
    p.risk_mm != null ? `Risk-adjusted surplus $${p.risk_mm}M` : "",
    p.downside_mm != null ? `Downside deviation $${p.downside_mm}M` : "",
    pb != null ? `Bust probability ${(pb * 100).toFixed(0)}%` : "",
  ].filter(Boolean).join(" · ");
  const bustStr = pb != null ? ` <span class="tm-dim" style="font-size:9px;">${(pb * 100).toFixed(0)}% bust</span>` : "";
  const val = p.sortino != null ? p.sortino : "-";
  return `<td class="tm-num tm-risk" title="${escapeHtml(tip)}"><span style="color:${col};">${val}</span>${bustStr}</td>`;
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
  _tbSyncSortSelect();
  _tbLastRows = rows;   // full filtered+sorted set for the Generate GFX board spec

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
      _crunchBanner = `<div style="margin:2px 0 6px;color:var(--text-secondary);font-size:11px;" title="Among this org's rostered and MLB board players; not a full 40-man census"><strong>${escapeHtml(_tbOrg)} <span data-gl="roster_crunch">roster crunch</span>:</strong> ${mustProtect} Rule 5 must-protect · ${squeezed} out-of-options on the 40-man</div>`;
    }
  }

  let html = `<div style="margin:6px 0 4px;color:var(--text-secondary);font-size:11px;">${rows.length} players · ${escapeHtml(_tbData.generated_at || "")}</div>
  ${_crunchBanner}
  ${topPager}
  <div class="tm-board-tablewrap mlbstats-scroll"><table class="stats-table tm-board-table">
  <thead><tr>
    <th class="mlbstats-col-rank">#</th>
    ${_tbTh("Player", "name")}
    ${_tbTh("Age", "age", "tm-num", "Current age (decimal years)")}
    ${_tbTh("Pos", "pos")}
    ${_tbTh("Org", "org")}
    ${_tbTh("FV", "fv", "tm-num", "Prospects only: eFV where graded, else consensus FV", false, "fv")}
    ${_tbTh("Grade", "surplus", "tm-num tm-col-div", "Trade Value Grade: the letter for the Surplus beside it, A+ to F. Sorts with Surplus.", true)}
    ${_tbTh("Surplus", "surplus", "tm-num", "$M of production above cost; same model as PROSPX and MLB Projections", false, "surplus_value")}
    ${showRisk ? _tbTh("Risk", "risk", "tm-num", "Sortino: expected surplus per unit of downside (higher is safer). Blank on a flat outcome fan; the bust probability still shows.", false, "risk_adjusted_surplus") : ""}
    ${_tbTh("Contract", "contract", "", "Club control: last controlled season · current salary. Where no salary path prices the row, its service-time phase instead, and the sort falls back to the debut+6 proxy. MiLB: the MLB deal on file, if any.", false, "club_control_window")}
    <th class="tm-col-div">Signals</th>
  </tr></thead><tbody>`;

  pagedRows.forEach((p, i) => {
    const rank = (curPage - 1) * pageSize + i + 1;
    const tv    = p.trade_value_mm;
    // ONE colour for the row, read off the VALUE, so the Surplus cell and the
    // letter chip beside it can never disagree. _tmValColor is _tbValTier with
    // the grey fallback, which is what an unpriced row painted before the ruler
    // (a bare _tbValTier returns "" there and emits `style="color:;"`).
    const tvCol = _tmValColor(tv);
    const grade = _tbGrade(tv);              // contract-adjusted surplus -> letter
    // FV only meaningful for active MiLB prospects - hide for MLB players
    const isProspect = p.status === "active";
    // eFV leads (round-to-NEAREST), consensus ceil as the fallback. The row
    // already carried xfv_grade and this column read only the consensus close,
    // so a prospect the board grades 60 showed 59 on the trade board while the
    // Grade column beside it was already ranking on xfv_grade. The rule now
    // lives in _tmFvNum, shared with the evaluator's search + seed sub-lines.
    const fv    = !isProspect ? "" : _tmFvNum(p.xfv_grade, p.fv);
    // Position: trade_values.json now carries fielding-corrected position
    const pos   = escapeHtml(p.position || "");
    const org   = escapeHtml(p.org || "");   // may be empty for some players
    const name  = escapeHtml(p.player_name || "?");
    const isMlb = _tbIsMlb(p);
    const statusCol = isMlb ? "var(--text-violet)" : "var(--neon-green)";
    const statusLbl = isMlb ? "MLB" : "MiLB";
    // Range tooltip. The band is NAMED, because two different ones ship: an eFV
    // credible interval on a prospect-era surplus, and (since 2026-08-03) the
    // projection's own p10-p90 WAR fan repriced with salary held fixed, which is
    // what gives a re-pointed veteran a range again. Formatted through _tbFmt
    // because a projection band can go negative and "$-63.6-$799.4M" is not a
    // range anyone can read.
    const lo = p.trade_value_lo, hi = p.trade_value_hi;
    // THE BOUNDS ARE PERCENTILES AND THE PRICE BESIDE THEM IS A MEAN, so the
    // price can sit outside its own range and the range can have no width at
    // all. The compute states the opposite contract ("We anchor off the point
    // estimate to guarantee lo <= tv <= hi") and then the re-point overwrites
    // both bounds with the eFV band, which carries no such guarantee. Measured
    // 2026-09-06: 3,957 of 6,432 rows carry a zero-width band and 592 carry one
    // that excludes the price in the cell beside it, because a grade-20 profile
    // busts 92% of the time and every dollar it is worth lives in the top
    // decile. The bounds are right. "Range $0.7M to $0.7M" was not a sentence
    // about them.
    // ASK C: "salary fixed" now has to say WHICH salary and which decision.
    // Every non-production input is held at its point value here - the salary
    // path, the award band and the club's non-tender decision - so the low end
    // reads "production at P10, club tenders the same seasons it tenders on the
    // mean path". The award's own uncertainty ships separately as
    // surplus_salary_band_mm, WAR held at the mean: one factor at a time, in
    // both directions.
    // THE SPAN (owner answers VAL2-Q3 and VAL2-Q3-REVIEW (b), 2026-09-30): the
    // range runs over every season the value prices, so a guarantee past the
    // projection's fifth printed season carries its range to its last season.
    // Those seasons ride the fifth season's P10/P90 chained along the champion
    // aging curve, and the P10 is never floored: a fifth season P10 below zero
    // carries on below zero. The fifth season is derived from the payload's own
    // season, like every other span on this page.
    const _bThru = p.salary_thru != null ? Number(p.salary_thru) : null;
    const _bLastH = _tbCurSeason() + 5;
    const _bDecl = Array.isArray(p.club_option_declined) && p.club_option_declined.length;
    const bandWhat = p.band_basis === "projection"
      ? `projection P10-P90 WAR fan over every season the value prices${_bThru != null ? ` (through ${_bThru})` : ""}, salary path and the non-tender decision both held at the mean path (every season at its own P10 together, so it is wide)`
        + (_bThru != null && _bThru > _bLastH
          ? `. The seasons past ${_bLastH} take the ${_bLastH} P10 and P90 chained along the champion aging curve; the P10 is not floored at zero, so a ${_bLastH} P10 below zero stays below zero (a season at or below zero WAR is worth $0, so at the low end that season costs his full salary)${_bDecl ? "; a declined club option season carries no range" : ""}`
          : "")
      // QCLC01 (2026-10-03): a debuted player no projection prices rides
      // his locked pre-debut eFV backgrade, and the band is that grade's, so
      // the row names the basis instead of reading like a prospect.
      : p.surplus_source === "xfv_backgrade"
        ? "locked prospect eFV backgrade (xfv_backgrade, provisional); no projection prices this row"
      : "eFV credible interval";
    let rangeTip = "";
    if (lo != null && hi != null) {
      rangeTip = (Number(hi) > Number(lo))
        ? `Range ${_tbFmt(lo)} to ${_tbFmt(hi)} · ${bandWhat}`
        : `More than 80% of modelled outcomes land at ${_tbFmt(lo)} · ${bandWhat}`;
      if (tv != null && Number(tv) > Number(hi)) {
        rangeTip += `. The ${_tbFmt(tv)} shown is the mean, which sits above the 90th percentile here (upside concentrated in the top decile)`;
      } else if (tv != null && Number(tv) < Number(lo)) {
        rangeTip += `. The ${_tbFmt(tv)} shown is the mean, which sits below the 10th percentile here`;
      }
    }
    const flash = p.flash || {};
    const injD  = p.injury_discount || 0;

    // Navigate to player detail: MLB players -> their MLB Projections page,
    // prospects -> their PROSPX page. If no key, no navigation. The whole row
    // stays clickable as a convenience, but the player name is a REAL anchor so
    // keyboard and screen-reader users can reach the player page too (the row
    // onclick preventDefaults the anchor and routes to the same destination).
    const nav = _tbNavTarget(p, isMlb);
    const href = nav
      ? (nav.mlb ? "/projections/#player=" : "/prospx/#player=") + encodeURIComponent(nav.key)
      : "";
    const rowClick = nav
      ? `onclick="event.preventDefault();_tmNavPlayer('${escapeHtml(nav.key)}',${nav.mlb});" style="cursor:pointer;"`
      : "";

    // Signals: status badge + ceiling flag + injury warning + GRPO breakout badge.
    let signals = `<span style="color:${statusCol};font-size:10px;">${statusLbl}</span>`;
    if (flash.is_bimodal) signals += ` <span style="color:var(--card-gold);font-size:10px;" title="Ceiling player (p_click=${flash.p_click})">↑</span>`;
    if (injD > 0.05)      signals += ` <span style="color:var(--neon-red);font-size:10px;" title="Injury discount ${(injD*100).toFixed(0)}%">⚕</span>`;
    signals += _tbCrunchChip(p.crunch);
    // BASIS CHIP. This row asked for an eFV backgrade and did not get one: it
    // has no salary on file, so there is nothing to price a control window over
    // and the fallback would have valued him off a grade he earned years ago as
    // a prospect. The price shown is this module's own bayes number instead.
    // Stamped by bayes_trade_value; rendered here because a basis change nobody
    // can see is indistinguishable from no change at all, which was the whole
    // argument for stamping it.
    if (p.efv_backgrade_withheld) {
      signals += ` <span style="color:var(--text-secondary);font-size:10px;" title="eFV backgrade withheld (${escapeHtml(String(p.efv_backgrade_withheld))}): no salary on file, so the price is the trade-value model's own number">&#8709;eFV</span>`;
    }
    // GRPO breakout badge - a within-cohort breakout SIGNAL (display only; it no longer
    // shifts the surplus, which is now the platform eFV/Projections value). Click -> group.
    const grpoSc = p.grpo_breakout_score;
    if (grpoSc != null && grpoSc >= 0.55) {   // only flag genuine breakout signals
      const grpoCol = grpoSc >= 0.70 ? "var(--neon-green)" : "var(--text-amber)";
      const grpoBord = grpoSc >= 0.70 ? "var(--neon-green)" : "var(--neon-amber)";
      signals += ` <button class="chip" style="padding:1px 5px;font-size:9px;color:${grpoCol};border-color:${grpoBord};"
        onclick="event.stopPropagation();_tbShowGroup('${escapeHtml(p.player_key||'')}');"
        title="GRPO within-cohort breakout score ${(grpoSc*100).toFixed(0)}% (${_TB_GRPO_VERDICT}; does not move the surplus). Click for the profile group.">
        ▲${(grpoSc*100).toFixed(0)}
      </button>`;
    }
    const addBtns = "";

    html += `<tr class="prospect-row" ${rowClick} title="${rangeTip}">
      <td class="tm-rank mlbstats-col-rank">${rank}</td>
      <td class="tm-player">${href ? `<a class="fa-player-link" href="${href}">${name}</a>` : name}</td>
      <td class="tm-num tm-dim">${p.age != null ? Number(p.age).toFixed(1) : "-"}</td>
      <td class="tm-dim">${pos}</td>
      <td><span class="tm-org-cell">${org ? _tmTeamLogo(org) : ""}<span class="tm-org-abbr">${org}</span></span></td>
      <td class="tm-num tm-dim">${fv}</td>
      <td class="tm-num tm-col-div tm-grade">${grade ? `<span class="tm-grade-chip" style="color:${tvCol};border-color:${tvCol};" title="Trade Value Grade ${grade} (${_tbFmt(tv)} contract-adjusted surplus)">${grade}</span>` : ""}</td>
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
  // Term spans get their tooltip + aria wiring here, after the board is in the
  // DOM. The table is rebuilt on every render, so this runs on every render.
  _tmWireGl(wrap);
  // Sortable column headers (the table is rebuilt each render, so rewire here).
  wrap.querySelectorAll("th[data-tb-sortcol]").forEach(th => {
    th.addEventListener("click", () => _tbSortByCol(th.dataset.tbSortcol));
    th.addEventListener("keydown", e => {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); _tbSortByCol(th.dataset.tbSortcol); }
    });
  });
}

// ── Generate GFX: board spec + chip ────────────────────────────────────────
// Condensed one-line Signals string for the shared board graphic (the on-screen
// column mixes colored badges + chips that don't survive to a flat canvas cell).
function _tmSignalsText(p) {
  const bits = [_tbIsMlb(p) ? "MLB" : "MiLB"];
  const flash = p.flash || {};
  if (flash.is_bimodal) bits.push("↑ ceiling");
  if ((p.injury_discount || 0) > 0.05) bits.push("IL");
  if (p.efv_backgrade_withheld) bits.push("no eFV backgrade");
  const c = p.crunch;
  if (c) {
    if (c.rule5_exposed) bits.push("R5");
    else if (c.on_40_man && c.options_left === 0) bits.push("0-opt");
    else if (c.on_40_man && c.options_left === 1) bits.push("1-opt");
  }
  const g = p.grpo_breakout_score;
  if (g != null && g >= 0.55) bits.push("▲" + (g * 100).toFixed(0));
  return bits.join(" · ");
}
// Board spec for EEPHUS_GFX.open, built from the CURRENT filtered+sorted array
// (_tbLastRows). Mirrors the fa.js / projections.js board-spec pattern.
function _tmBoardSpec(rows) {
  const src = rows || [];
  const brows = src.map((p, i) => {
    const tv = p.trade_value_mm;
    const grade = _tbGrade(tv);
    let risk;
    if (p.sortino == null) { risk = { t: "-", c: "muted" }; }
    else {
      const pb = p.p_bust;
      const rc = pb == null ? null : pb >= 0.25 ? "red" : pb <= 0.10 ? "green" : null;
      risk = rc ? { t: String(p.sortino), c: rc } : { t: String(p.sortino) };
    }
    const sub = [p.position, p.org, p.age != null ? Number(p.age).toFixed(1) : null]
      .filter(Boolean).join(" · ");
    return { cells: [
      { t: i + 1 },
      { t: p.player_name || "?", sub: sub || undefined },
      { t: grade || "-", c: "accent" },
      { t: tv == null ? "-" : _tbFmt(tv), c: tv == null ? "muted" : (tv >= 0 ? "green" : "red") },
      risk,
      { t: _tmSignalsText(p) },
    ] };
  });
  const filt = [];
  if (_tbPool !== "all") filt.push(_tbPool === "mlb" ? "MLB only" : "MiLB only");
  if (_tbTier !== "all") filt.push(_tbTier + " tier");
  if (_tbPos !== "all") filt.push(_tbPos);
  if (_tbExactPos !== "all") filt.push(_tbExactPos);
  if (_tbOrg !== "all") filt.push(_tbOrg);
  if (_tbQ) filt.push('"' + _tbQ + '"');
  return {
    kind: "board", module: "Trade Machine", accentToken: "--accent-cyan",
    title: "Trade Machine · Trade-Value Board",
    subtitle: `${src.length} players${filt.length ? " · " + filt.join(" · ") : ""}`,
    url: "eephus.io/trademachine", filenameBase: "eephus-trademachine-board",
    caption: "Bayesian surplus · contract-aware · positional scarcity · opt-out adjusted",
    board: {
      defaultCount: 25, counts: [10, 25, 50],
      legend: "Surplus = NPV surplus over each player's controlled seasons ($M)",
      columns: [
        { label: "#", frac: 0.05 },
        { label: "Player", frac: 0.32 },
        { label: "Grade", frac: 0.10 },
        { label: "Surplus $M", frac: 0.14 },
        { label: "Risk", frac: 0.13, wideOnly: true },
        { label: "Signals", frac: 0.26, wideOnly: true },
      ],
      rows: brows,
    },
  };
}
// Inject the "Generate GFX" chip next to the Trade Board's Filter & Sort row
// (the same .filter-toggle-row PROSPX hangs its list GFX buttons off). Idempotent.
function _tbInjectGfxChip() {
  if (!window.EEPHUS_GFX || !window.EEPHUS_GFX.chipHTML) return;
  if (document.getElementById("tm-board-gfx")) return;
  const sec = document.getElementById("proj-view-trademachine");
  const row = (sec || document).querySelector(".filter-toggle-row");
  if (!row) return;
  row.insertAdjacentHTML("beforeend", window.EEPHUS_GFX.chipHTML("tm-board-gfx", "Generate GFX"));
  const btn = document.getElementById("tm-board-gfx");
  if (btn) {
    btn.style.marginLeft = "8px";
    btn.onclick = () => window.EEPHUS_GFX.open(_tmBoardSpec(_tbLastRows));
  }
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
  if (sortSel) sortSel.addEventListener("change", () => { _tbSort = sortSel.value || null; resetPage("tradeboard"); _renderTBRows(); });
}

// AUDIT 2026-07-18 (A10): a renderTradeBoard() lived here - dead code that
// duplicated mount()'s entire fetch / wire / GRPO-sidecar block and was never
// referenced (mount() is the sole entry point, exported as
// window.TradeMachine.mount). Removed to keep one board-boot path.

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
        : "Profile-group data is unavailable; the breakout score on the chip stands."
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
      const bsCol = (m.breakout_score || 0) >= 0.60 ? "var(--neon-green)" : (m.breakout_score || 0) >= 0.45 ? "var(--text-amber)" : "var(--text-secondary)";
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
        // The eFV grade the board's FV column leads with. Dropped here, so the
        // evaluator's search fell back to the raw consensus close and showed a
        // different FV for the same prospect.
        xfv_grade: p.xfv_grade != null ? p.xfv_grade : null,
        surplus: { value_mm: p.posterior_surplus_mm }
      }));
    // Valued MLB rows, kept for search. The prospect pool above drops every
    // graduated/debuted row, and the MLB search path only sees players whose
    // mlb_player_detail entry carries a projection surplus. 840 players were
    // therefore valued on the board and findable NOWHERE, including Jose
    // Quintana, Yoan Moncada, Gleyber Torres and Gavin Lux. The board is the
    // authority on whether a player has a price, so let it answer.
    // Keyed by the projection key where the row carries one, so the search's
    // de-duplication against mlb_player_detail compares one human to himself.
    DATA.mlbBoard = (d.players || [])
      .filter(p => p && _tbIsMlb(p) && p.posterior_surplus_mm != null)
      .map(p => ({
        player_key: (p.proj_key || p.player_key), player_name: p.player_name,
        position: p.position, org: p.org,
        mm: p.posterior_surplus_mm, source: p.surplus_source || null
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
    // The lamp loader holds the board's place until trade values arrive; the
    // first board render replaces it.
    const lw = document.getElementById("tradeboard-content");
    if (lw && window.EephusState) lw.innerHTML = window.EephusState.html("loading", "Loading the trade-value board...");
    fetch(DATA_BASE + "trade_values.json", { cache: "no-cache" })
      .then(r => { if (!r.ok) throw new Error(r.status); return r.json(); })
      .then(d => {
        _tbData = d; window._tbData = d;
        // Vets we model but cannot price (expiring contract / none on file).
        // Kept out of the board's value ranking, kept IN search so a real
        // major-leaguer never returns silence.
        _TM.unpriced = d.unpriced || [];
        _tmBuildProspectPool(d);
        _tbPopulateSelectFilters();
        _renderTBRows();
        _tbWireFilters();
        _tbInjectGfxChip();     // "Generate GFX" chip beside the board filters
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
        // The Club Ledger's CBT slice for the evaluator's CBT block (M27-4).
        // Non-blocking and optional: without it the block simply does not show.
        fetch(DATA_BASE + "trade_cbt.json", { cache: "no-cache" })
          .then(r => r.ok ? r.json() : null)
          .then(c => { if (c && c.clubs) { _TM.cbt = c; renderTradeMachine(); } })
          .catch(() => { /* enrichment only */ });
        _tbWireFilterToggle();
      })
      .catch(() => {
        const w = document.getElementById("tradeboard-content");
        if (w) w.innerHTML = '<div class="empty-state">This view is temporarily unavailable. Check back shortly.</div>';
      });
  }

  window.TradeMachine = { mount: mount };
})();
