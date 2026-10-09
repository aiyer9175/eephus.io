/* Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
 * Unauthorized copying of this file, via any medium is strictly prohibited
 * Proprietary and confidential
 * Written by Noah J. Dengler (@ARKNDJL), 2026 */

// =============================================================================
// eephus.io Free Agency app (/fa/) - Class Board / Team Fits / Archive /
// Model Accountability / Glossary
// =============================================================================
// A standalone surface, SEPARATE from PROSPX by design: it shares the site
// chrome (assets/site.css) and the data/ directory but loads none of the
// PROSPX boot payload and none of its script. Fed by the three fa_export.py
// sidecars (fa_class.json / fa_archive.json / fa_meta.json) fetched directly
// from /data/. Two numbers, never conflated: RATIONAL VALUE (convex-priced
// NPV of the gated projection) vs PREDICTED MARKET (projLength /
// projGuarantee / projAAV with P10-P90 bands). Contract Surplus ($) =
// rational − predicted; the VERDICT chip (value / market / overpay) reads
// Deal+ against the historical corpus terciles.
(function () {
  "use strict";

  const EM_DASH = " - ";
  const D = {};            // loaded sidecars by name
  const _inflight = {};

  // Mirror of PROSPX's formatMetric for the types this surface renders - 
  // same precision rules, same null token, same -0 collapse. Kept local so
  // the FA page never imports PROSPX script.
  function formatMetric(value, type = "int") {
    const n = Number(value);
    if (value == null || value === "" || !Number.isFinite(n)) return EM_DASH;
    const z = n === 0 ? 0 : n;                       // collapse -0 -> 0
    const sign = z > 0 ? "+" : (z < 0 ? "-" : "");   // zero is unsigned
    const abs = Math.abs(z);
    // A value that ROUNDS to zero at the printed precision is zero and prints
    // unsigned. toFixed keeps the sign of a tiny negative, so -0.01 at one
    // decimal printed "-0.0" (218 board cells on /projections/, 2026-10-02), and
    // the signed types put a "+" or "-" on a printed 0.00. Both helpers read
    // the ROUNDED figure, never z itself.
    const fixed = (x, d) => (Number(x.toFixed(d)) === 0 ? (0).toFixed(d) : x.toFixed(d));
    const signAt = d => (Number(abs.toFixed(d)) === 0 ? "" : sign);
    switch (type) {
      case "int":      return String(Math.round(z));
      case "war":      return fixed(z, 1);
      case "rate":     return signAt(2) + abs.toFixed(2);
      case "surplusM": return signAt(1) + "$" + abs.toFixed(1) + "M";
      // MINUS but never PLUS. Dropping the sign entirely was harmless for the
      // guarantees and AAVs this surface passes it (all positive) but rendered
      // a NEGATIVE dollar figure as a positive one, and /projections/ prices
      // surplus through this same type, where negatives are now common
      // (rest-of-season control pricing, 2026-08-03). A liability shown as an
      // asset is the worst possible rounding of that number. The leading "+"
      // that `sign` would add belongs to surplusM, where the direction is the
      // point; on a contract guarantee it is noise.
      case "moneyM":   return (z < 0 && signAt(1) ? "-" : "") + "$"
                            + (abs >= 100 ? abs.toFixed(0) : abs.toFixed(1)) + "M";
      case "pct":      return fixed(z, 1) + "%";
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
  // The pixel state box (assets/eephus-state.js, final-pass plan 5.7 PX-12):
  // loading, empty, unmeasured or failed, around a message this file escapes.
  // The bare box is the fallback for a test harness that loads this file alone.
  function pxState(kind, msg, opts) {
    var S = typeof window !== "undefined" && window.EephusState;
    if (S) return S.html(kind, msg, opts);
    var cls = typeof opts === "string" ? opts : (opts && opts.cls) || "";
    return '<div class="px-state is-' + kind + (cls ? " " + cls : "") + '"' +
      (kind === "failed" ? ' role="alert"' : "") + '><div class="px-state-msg">' + msg + "</div></div>";
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
  // QMLP08: the mark is drawn at 13 to 16 px, so it is asked for at 32 px
  // through ESPN's combiner (the shared EEPHUS_HUB size rule) rather than as the
  // 500 x 500 master, which was 27 files and 1.05 MB, about half the page.
  const FA_LOGO_PX = 32;
  function teamLogoSrc(org) {
    const H = typeof window !== "undefined" && window.EEPHUS_HUB;
    const viaHub = H && H.teamLogoURL ? H.teamLogoURL(org, FA_LOGO_PX) : "";
    return viaHub || "https://a.espncdn.com/combiner/i?img=/i/teamlogos/mlb/500/"
      + `${ESPN_SLUGS[org]}.png&h=${FA_LOGO_PX}&w=${FA_LOGO_PX}`;
  }
  function teamLogo(org) {
    if (!org || !ESPN_SLUGS[org]) return "";
    return `<img class="fa-logo" src="${esc(teamLogoSrc(org))}" alt="${esc(org)}" loading="lazy" onerror="this.remove()">`;
  }
  // A club mention links to the club's Franchises page (owner ask 9) through
  // the hub's one club resolver (EEPHUS_HUB.club + clubHref), never a raw
  // payload code. `inner` is the markup printed before (the mark, the code).
  // opts.mark makes a mark that sits beside its own linked code a mouse twin
  // (out of the tab order, hidden from a screen reader). A code the hub does
  // not know keeps its markup, in a span marked data-club-nolink="unresolved"
  // when it carries a mark, never a guessed link.
  function clubA(org, inner, opts) {
    const o = opts || {};
    const H = typeof window !== "undefined" && window.EEPHUS_HUB;
    if (!inner || !H || !H.club || !H.clubHref) return inner;
    const c = org ? H.club(org) : null;
    if (!c) return org ? `<span data-club-nolink="unresolved">${inner}</span>` : inner;
    return `<a class="club-link${o.cls ? " " + o.cls : ""}${o.mark ? " club-link--mark" : ""}" href="${esc(H.clubHref(c.code))}" data-club="${c.code}"`
      + ` title="${esc(c.name + ": franchise overview")}"`
      + (o.mark ? ` tabindex="-1" aria-hidden="true"` : "") + `>${inner}</a>`;
  }
  // A code that prints as text, linked.
  function clubLink(org) {
    if (!org) return "";
    return clubA(org, esc(org), { cls: "fa-club-link" });
  }
  // The mark and its code as one link; the mark is decorative beside the code.
  function clubTag(org) {
    if (!org) return "";
    return clubA(org, logoMark(org) + esc(org), { cls: "fa-club-link" });
  }
  function logoMark(org) {
    if (!org || !ESPN_SLUGS[org]) return "";
    return `<img class="fa-logo" src="${esc(teamLogoSrc(org))}" alt="" loading="lazy" onerror="this.remove()">`;
  }
  // A mark standing alone (no code beside it): the link's name is the club's
  // full name, and a mark that fails to load leaves the code behind.
  function clubMark(org) {
    const H = typeof window !== "undefined" && window.EEPHUS_HUB;
    const c = org && H && H.club ? H.club(org) : null;
    if (!c || !ESPN_SLUGS[org]) return clubA(org, teamLogo(org));
    return clubA(org, `<img class="fa-logo" src="${esc(teamLogoSrc(org))}" alt="${esc(c.name)}" loading="lazy"`
      + ` onerror="this.replaceWith('${c.code}')">`);
  }

  // Deal verdict chip - the plain-English read of Deal+ (band edges are the
  // 2015-2026 corpus terciles; see the deal_verdict glossary entry).
  // WHAT A CHIP MEANS IS DECIDED SERVER-SIDE, SO THE TOOLTIP READS IT rather
  // than restating it from memory. These strings used to hardcode the POOLED
  // terciles 109/223, which are wrong twice over: the served board has banded
  // verdicts PER POSITION GROUP since 2026-07-30 (owner decision,
  // fa_market.VERDICT_BAND_MODE = "group"), and the pooled edges themselves were
  // re-cut 109/223 -> 89/198 on 2026-08-19.
  //
  // Measured 2026-09-06: 60 of the 232 served chips carried a Deal+ that the
  // tooltip's own numbers put in a DIFFERENT bucket. Sandy Alcantara, Deal+ 191,
  // chipped VALUE beside a sentence saying value starts at 223. ZERO of the 232
  // disagree with the live group edges, so the verdicts were right the whole
  // time and only the sentence was wrong. Deriving it means it cannot go stale
  // behind a re-cut again.
  const VERDICT_LABEL = { value: "VALUE", market: "MARKET", overpay: "OVERPAY" };
  const VERDICT_WHAT = {
    value: "Rational value above the predicted price",
    market: "Rational value and predicted price in the middle tercile",
    overpay: "Predicted price above rational value",
  };
  // fa_market._pos_group, mode v1 (the shipped four buckets). test_fa_verdict_
  // tooltip.py reads the Python constants and fails if these drift apart.
  function _faPosGroup(pos) {
    const head = String(pos || "").toUpperCase().split("/")[0].trim();
    if (["SP", "SP2", "P", "LHP", "RHP"].indexOf(head) >= 0) return "SP";
    if (["RP", "CL", "SIRP", "MIRP"].indexOf(head) >= 0) return "RP";
    if (head === "C") return "C";
    return "POS";
  }
  // The band THIS row's verdict was actually cut on, read off the artifact.
  function _faVerdictBand(pos) {
    const e = ((D.fa_meta || {}).gate2 || {}).verdict_edges;
    if (!e) return null;
    const pooled = e.pooled || {};
    let lo = pooled.overpay_max, hi = pooled.value_min, basis = "corpus-wide";
    if (e.band_mode === "group" && e.group) {
      const g = e.group[_faPosGroup(pos)];
      if (g && g.length === 2) { lo = g[0]; hi = g[1]; basis = _faPosGroup(pos) + " group"; }
    }
    return (lo == null || hi == null) ? null : { lo: lo, hi: hi, basis: basis };
  }
  function verdictChip(m) {
    const label = VERDICT_LABEL[m.verdict];
    if (!label) return EM_DASH;
    const b = _faVerdictBand(m.pos);
    let band = ".";
    if (b) {
      const where = m.verdict === "value" ? `Deal+ at or above ${b.hi}`
                  : m.verdict === "overpay" ? `Deal+ below ${b.lo}`
                  : `Deal+ ${b.lo} to ${b.hi}`;
      band = ` (${where}, ${b.basis} terciles).`;
    }
    return `<span class="fa-verdict fa-verdict-${m.verdict}" data-gl="deal_plus" title="${VERDICT_WHAT[m.verdict]}${band} Deal+ ${m.dealPlus ?? "?"}.">${label}</span>`;
  }
  // A surplus number is FORMATTED in one place and the band sentence is COMPOSED
  // in one place. Every surface reads these: the cell, its aria-label (which
  // openBand prints verbatim), its title, and the row detail line, which needs
  // the same three strings in the "X &middot; P10-P90 A to B" shape its sibling
  // groups use. `lo` and `hi` are null when the row has no band, so no caller
  // has to invent a zero for an end the model never produced.
  function surplusBandParts(usd, p10, p90) {
    if (usd == null) return null;
    const fmt = v => formatMetric(v / 1e6, "surplusM");
    return {val: fmt(usd), lo: p10 == null ? null : fmt(p10), hi: p90 == null ? null : fmt(p90)};
  }
  function surplusBandText(usd, p10, p90) {
    const b = surplusBandParts(usd, p10, p90);
    if (b == null || b.lo == null || b.hi == null) return null;
    return `Surplus ${b.val}. P10 to P90 of simulated contract value: ${b.lo} to ${b.hi}.`;
  }
  function surplusSpan(usd, p10, p90) {
    const b = surplusBandParts(usd, p10, p90);
    if (b == null) return EM_DASH;
    const cls = usd >= 0 ? "fa-pos" : "fa-neg";
    // Same treatment the AAV and Yrs/Guar cells got: the band was hover-only
    // here, which is invisible on a phone and inconsistent for screen readers.
    const band = surplusBandText(usd, p10, p90);
    if (band == null) return `<span class="${cls}">${b.val}</span>`;
    return `<span class="${cls}" data-band tabindex="0" aria-label="${esc(band)}" title="${esc(band)}">${b.val}</span>`;
  }

  // TAP-TO-OPEN BANDS (2026-08-07). The P10-P90 ranges got aria-label plus
  // tabindex last pass, which closed the keyboard and screen-reader half of the
  // gap and said so; the visible half was still a `title`, and no touch device
  // shows one. So a phone reader could not see a band at all.
  //
  // The panel text is READ OFF the cell's aria-label rather than rebuilt here.
  // That is the whole design: the aavWild disclosure (the bands are a flat ratio
  // rather than a per-tier fit, so the top of the market gets a P90 no contract
  // has ever reached) is composed once, at the cell, and cannot drift out of
  // sync with the copy assistive tech reads. Rebuilding it here would be a
  // second copy of a known-wrong number's warning label.
  let _bandPop = null;
  let _bandDismissWired = false;
  function closeBand() { if (_bandPop) _bandPop.hidden = true; }
  function openBand(cell) {
    const text = cell.getAttribute("aria-label");
    if (!text) return;
    if (!_bandPop) {
      _bandPop = document.createElement("div");
      _bandPop.className = "fa-band-pop";
      // aria-hidden, not role="dialog": this panel is the VISUAL half of a
      // disclosure whose text is already the cell's own aria-label. Exposing it
      // would read the same sentence twice, and a dialog role would promise
      // focus management it does not do.
      _bandPop.setAttribute("aria-hidden", "true");
      _bandPop.hidden = true;
      document.body.appendChild(_bandPop);
    }
    _bandPop.textContent = text;
    _bandPop.hidden = false;
    const r = cell.getBoundingClientRect();
    // Page coordinates, not viewport: the panel is absolutely positioned so it
    // rides the document. Any scroll closes it (below) because the cell can
    // also move inside .fa-board-main's own scroller.
    const w = _bandPop.offsetWidth;
    const left = Math.max(8, Math.min(r.left + window.scrollX,
                                      window.scrollX + document.documentElement.clientWidth - w - 8));
    _bandPop.style.left = `${left}px`;
    _bandPop.style.top = `${r.bottom + window.scrollY + 6}px`;
  }
  // Dismissal is wired ONCE for the module, not per render: renderBoard replaces
  // the rows wholesale and would otherwise stack a listener per repaint.
  function wireBandDismiss() {
    if (_bandDismissWired) return;
    _bandDismissWired = true;
    // Bubble phase. A cell's own handler calls stopPropagation, so a click that
    // opened a panel never reaches this and cannot close what it just opened.
    document.addEventListener("click", e => {
      if (!_bandPop || _bandPop.hidden) return;
      if (e.target.closest && e.target.closest(".fa-band-pop")) return;
      closeBand();
    });
    document.addEventListener("keydown", e => { if (e.key === "Escape") closeBand(); });
    window.addEventListener("resize", closeBand);
    document.addEventListener("scroll", closeBand, true);
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

  // ---- URL state ------------------------------------------------------------
  // #view=board|tracker|fits|archive|model|glossary (&team= / &winter=), or
  // #player=<key> for the FA player card (rides on top of the current view).
  const VIEWS = [["board", "Class Board"], ["tracker", "Signing Tracker"],
                 ["fits", "Team Fits"], ["archive", "Archive"],
                 ["model", "Model Accountability"]];
  const state = { view: "board", team: null, winter: null, player: null,
                classYear: null };   // null = the CURRENT class (default)

  function syncFromURL() {
    const p = new URLSearchParams(window.location.hash.slice(1));
    // The FA glossary view moved into the unified module - redirect deep links.
    if (p.get("view") === "glossary") {
      window.location.replace("/glossary/#cat=" + encodeURIComponent("Free Agency"));
      return;
    }
    if (p.has("view") && VIEWS.some(([k]) => k === p.get("view"))) state.view = p.get("view");
    if (p.has("team")) state.team = p.get("team");
    if (p.has("winter")) state.winter = Number(p.get("winter")) || null;
    state.classYear = Number(p.get("class")) || null;
    state.player = p.get("player") || null;
    // Board sort and filters ride the hash, so a sorted or filtered class
    // board is shareable. Keys absent from the hash keep their current
    // value: Back must not silently clear a filter, and a hash with neither
    // sort nor dir must not reset the direction the reader chose.
    if (p.has("sort")) boardState.sort = FA_SORT_KEYS.indexOf(p.get("sort")) >= 0 ? p.get("sort") : "projGuar";
    if (p.has("dir") || p.has("sort")) {
      boardState.dir = p.get("dir") === "asc" ? 1 : p.get("dir") === "desc" ? -1 : faNaturalDir(boardState.sort);
    }
    ["type", "pos", "verdict", "hand"].forEach(k => { if (p.has(k)) boardState[k] = p.get(k); });
  }

  function syncToURL() {
    const p = new URLSearchParams();
    if (state.classYear) p.set("class", String(state.classYear));
    if (state.player) p.set("player", state.player);
    else {
      if (state.view !== "board") p.set("view", state.view);
      if (state.view === "fits" && state.team) p.set("team", state.team);
      if (state.view === "archive" && state.winter) p.set("winter", String(state.winter));
      if (state.view === "board") {
        if (boardState.sort !== "projGuar") p.set("sort", boardState.sort);
        if (boardState.dir !== faNaturalDir(boardState.sort)) p.set("dir", boardState.dir > 0 ? "asc" : "desc");
        ["type", "pos", "verdict", "hand"].forEach(k => { if (boardState[k] !== "all") p.set(k, boardState[k]); });
      }
    }
    const h = p.toString();
    history.replaceState(null, "", h ? `#${h}` : window.location.pathname);
  }

  async function render() {
    const rows = document.getElementById("fa-rows");
    const chips = document.getElementById("fa-view-chips");
    const banner = document.getElementById("fa-banner");
    if (!rows) return;
    // The view pills are tabs over #fa-rows (X06-23): one tablist, exactly one
    // tab selected. The Library link and the winter group sit outside it.
    chips.innerHTML = `<span class="fa-view-tabs" role="tablist" aria-label="Free Agency views">`
      + VIEWS.map(([k, label]) => {
        const on = state.view === k;
        return `<button type="button" class="chip${on ? " active" : ""}" data-fa-view="${k}" role="tab" aria-selected="${on}" aria-controls="fa-rows">${label}</button>`;
      }).join("") + `</span>`
      + ` <a class="chip" href="/glossary/#cat=${encodeURIComponent("Free Agency")}" title="Free Agency terms in the Library"><span class="chip-glyph" aria-hidden="true">${window.EephusIco ? window.EephusIco("library", 12) : ""}</span>Library</a>`;
    chips.querySelectorAll("[data-fa-view]").forEach(b => b.onclick = () => {
      state.view = b.dataset.faView; state.player = null; syncToURL(); render();
    });
    // Winter selector - current class is the default; future winters are
    // the SAME constructed-class pipeline run on Spotrac's forward pages
    // (projected members; the signing tracker goes live with the winter).
    const curYear = (D.fa_meta && D.fa_meta.class_year) || (D.fa_class && D.fa_class.class_year) || new Date().getFullYear() + 1;
    const winters = [null, curYear + 1, curYear + 2];
    const wchips = winters.map(y => {
      const label = y ? `${y - 1}-${String(y).slice(2)}` : `${curYear - 1}-${String(curYear).slice(2)}`;
      const on = (state.classYear || null) === y;
      return `<button type="button" class="chip${on ? " active" : ""}" data-fa-class="${y || ""}" aria-pressed="${on}" title="${y ? "Projected future class (no signings yet)" : "The current winter (default)"}">${label}${y ? "" : " ·"}</button>`;
    }).join("");
    const wrap = document.createElement("span");
    wrap.style.cssText = "margin-left:14px;display:inline-flex;gap:4px;align-items:center;";
    wrap.innerHTML = `<span class="filter-label">Winter</span>${wchips}`;
    chips.appendChild(wrap);
    wrap.querySelectorAll("[data-fa-class]").forEach(b => b.onclick = () => {
      state.classYear = Number(b.dataset.faClass) || null;
      state.player = null; syncToURL(); render();
    });
    // QMLP04: tall views hold one viewport while they load (site.css .fa-hold).
    rows.classList.toggle("fa-hold", !state.player && state.view !== "tracker");
    rows.innerHTML = pxState("loading", "Loading the free-agent board.");
    const clsName = state.classYear ? `fa_class_${state.classYear}` : "fa_class";
    // QMLP12: only the Archive view reads fa_archive (its table, rail and GFX
    // caption), so every other view paints without waiting on its 326 KB and
    // fetches it once the page is idle.
    const needArchive = state.view === "archive" && !state.player;
    try {
      const want = [load(clsName), load("fa_meta")];
      if (needArchive) want.push(load("fa_archive"));
      await Promise.all(want);
    } catch (e) {
      if (state.classYear) {
        rows.innerHTML = `<div class="state-message">The ${state.classYear - 1}-${String(state.classYear).slice(2)} class is not on this deploy. <a href="#" onclick="location.hash='';return false;">Back to the current class</a>.</div>`;
        return;
      }
      rows.innerHTML = pxState("failed", `Free-agent board did not load. Retry; the nightly build may be writing it.
        <button class="chip" id="fa-retry" type="button">Retry</button>`);
      const retry = document.getElementById("fa-retry");
      if (retry) retry.onclick = () => render();   // load() re-fetches: failures are not cached
      return;
    }
    const cls = D[clsName], meta = D.fa_meta;
    if (!cls || !cls.members) {
      rows.innerHTML = `<div class="state-message">Free-agent board not built yet on this deploy; the nightly build writes it.</div>`;
      return;
    }
    if (ilLive()) await loadIl(cls);
    _faPhotoLegacy = !cls.members.some(m => m.mlbam);
    const futureNote = state.classYear
      ? `<div class="fa-cba-note">&#9432; ${state.classYear - 1}-${String(state.classYear).slice(2)} is a projected class: contract-expiry members with option and QO statuses, priced at that winter's ex-ante <span data-gl="winter_dpw">$/WAR</span>. No signings yet.</div>`
      : "";
    banner.innerHTML = futureNote + (cls.cba_carry_forward
      ? `<div class="fa-cba-note">${window.EephusIco ? window.EephusIco("warn", 12) : ""} CBA past 2026-12-01 <span data-gl="cba_carry_forward">carried forward</span>: thresholds and QO values not yet bargained.</div>`
      : "") + freshnessLine(meta);
    if (window.EEPHUS_GL) window.EEPHUS_GL.wire(banner);
    if (state.player) { renderPlayer(rows, cls, state.player); }
    else if (state.view === "board") renderBoard(rows, cls);
    else if (state.view === "tracker") renderTracker(rows, cls);
    else if (state.view === "fits") renderFits(rows, cls, meta);
    else if (state.view === "archive") renderArchive(rows);
    else renderModel(rows, meta);
    // Term spans ([data-gl]) get tooltip + aria wiring from the shared
    // glossary runtime; definitions come from the unified data layer.
    if (window.EEPHUS_GL) window.EEPHUS_GL.wire(rows);
    if (!needArchive && !D.fa_archive) {
      const later = window.requestIdleCallback || (fn => window.setTimeout(fn, 1500));
      later(() => { load("fa_archive").catch(() => { /* the Archive view retries on open */ }); });
    }
  }

  function statusChip(m) {
    if (m.status === "signed") {
      const terms = m.signedMilb ? "MiLB deal"
        : `${m.signedYears ?? "?"}y / ${money(m.signedGuar)}`;
      return `<span title="Signed${m.signedDate ? ", first seen " + m.signedDate + " (pipeline observation date)" : ""}.">SIGNED ${esc(m.signedTo || "")} ${terms}</span>`;
    }
    if (m.status === "option_exercised") {
      return `<span title="Option exercised; never reached the market (first-seen heuristic).">option exercised</span>`;
    }
    if (m.status === "locked") return `<span title="Contract expires; locked into the class.">UFA</span>`;
    const pct = m.enterProb != null ? ` &middot; P(enter) ${(m.enterProb * 100).toFixed(0)}%` : "";
    const price = m.optPrice ? ` $${(m.optPrice / 1e6).toFixed(1)}M` : "";
    const src = m.enterProbSrc && m.enterProbSrc.startsWith("band_priced")
      ? "P(enter) from the option price against the predicted AAV band (v2)."
      : "P(enter) from the v1 heuristic (mutual and conditional options keep explicit priors).";
    return `<span title="Option pending: membership is probabilistic until it resolves. ${src}">${esc((m.type || "").replace(/_/g, " "))}${price}${pct}</span>`;
  }

  // A5: in-module deep links (player cards, rail, value-map, back-to-board) must
  // carry the active future-class param, or a click while a non-current winter is
  // selected drops class= - syncFromURL then reloads the CURRENT class and the
  // #player card is the wrong player or missing entirely. Prefixes the hash query
  // (class first, matching syncToURL's canonical order) so every in-module jump
  // stays in the same winter. Empty string on the default (current) class.
  function faHash() {
    return state.classYear ? `class=${state.classYear}&` : "";
  }

  // ---- handedness -----------------------------------------------------------
  // Class rows carry a single letter in `bt`, and it means DIFFERENT things by
  // role: for position players it is the bat side, for pitchers the throwing
  // hand. Verified against the shipped leaderboards before this shipped - the
  // FA hitters agree with hitter_leaderboards `bats` on 85/85 overlapping
  // names, and the FA pitchers agree with the PAL reverse-platoon `p_throws`
  // on 110/110. So the label is role-aware and never claims both.
  function isPitcherRow(m) {
    const g = posGroup(m);
    return g === "SP" || g === "RP";
  }
  function handOf(m) {
    const v = String(m.bt || "").trim().toUpperCase();
    return (v === "L" || v === "R" || v === "S") ? v : null;
  }
  function handLabel(m) {
    const h = handOf(m);
    if (!h) return null;
    if (isPitcherRow(m)) return h === "S" ? "Switch-throws" : `Throws ${h}`;
    return h === "S" ? "Switch-hitter" : `Bats ${h}`;
  }
  // Compact board form: T:L for arms, B:R for bats, so the column scans.
  function handShort(m) {
    const h = handOf(m);
    if (!h) return "";
    return `<span class="fa-hand" title="${esc(handLabel(m))}">${isPitcherRow(m) ? "T" : "B"}:${h}</span>`;
  }

  // The 24px headshot well, always emitted so an async fill cannot shift the
  // layout. Two placements, and the difference is not cosmetic: inside
  // .mlb-name it is an inline box that costs 7px of LINE BOX and sits inside
  // the ellipsis box, where text-overflow can eat it (measured and written up
  // on .proj-id in site.css). On the board card it is a grid RAIL beside the
  // name instead; the tracker and fits TABLES keep it inline, where there is no
  // line-box budget to protect.
  // QMLP10: the class payload carries each resolved member's mlbam, so the
  // headshot is drawn with the row. A payload written before the field existed
  // (no member carries one) keeps the old async fill from the links map.
  let _faPhotoLegacy = false;
  function rowPhoto(m) {
    if (m.mlbam) {
      // .fa-row-headshot is 24x24.
      return `<span class="fa-row-photo"><img class="fa-row-headshot" loading="lazy" src="${faHeadshotURL(m.mlbam, 24)}" alt="" onerror="this.remove()"></span>`;
    }
    return _faPhotoLegacy
      ? `<span class="fa-row-photo" data-photo-key="${esc(m.key || "")}"></span>`
      : `<span class="fa-row-photo"></span>`;
  }
  function playerLink(m, opts) {
    // title carries the full name: at phone widths the shared .mlb-name box
    // ellipsizes the trailing type tag/badges, and the tooltip is the only
    // place the cut text can still be read.
    const photo = opts && opts.noPhoto ? "" : rowPhoto(m);
    return `<a href="#${faHash()}player=${encodeURIComponent(m.key || "")}" class="fa-player-link" title="${esc(m.name)}">${photo}<strong>${esc(m.name)}</strong></a>`;
  }

  // Headshot URL builder for this module. ONE place, so a CDN transform
  // lockdown is a one-line revert here.
  //
  // 2026-08-04d: every FA headshot box is SQUARE (24px board rows, the 96px
  // hero, the 132px card hero) while the source images are 480x720 (2:3). The
  // DOM boxes were papering over that with object-fit:cover - which crops the
  // top of the head off, since it centres a 2:3 portrait in a square - and the
  // shared card canvas (eephus-hub.js, `g.drawImage(img, x, y, S, S)`) could
  // not paper over it at all: canvas drawImage has no object-fit, so it drew
  // the 2:3 source into a square and VERTICALLY SQUASHED every face.
  //
  // img.mlbstatic.com is Cloudinary and honours `c_fill,g_face`: it returns
  // EXACTLY the requested box, cropped around the detected face. Asking for the
  // real box fixes both, and needs zero canvas-code change.
  //
  // The `d_people:generic` default is DELIBERATELY dropped: it serves a
  // silhouette at HTTP 200, which means onerror never fires and the canvas
  // draws a squashed generic body. Without it a missing photo 404s, so the row
  // removes itself / the hero hides / the card simply omits the photo.
  const FA_FACE_CROP = "c_fill,g_face";
  function faHeadshotURL(mlbam, boxW, boxH) {
    if (!mlbam) return null;
    const w = Math.round(boxW * 2), h = Math.round((boxH || boxW) * 2);  // 2x retina + 2x canvas scale
    return "https://img.mlbstatic.com/mlb-photos/image/upload/"
      + `${FA_FACE_CROP},w_${w},h_${h},q_auto:best/v1/people/${mlbam}/headshot/67/current`;
  }

  // Legacy board-row headshots: filled async from the cross-module links map,
  // only for a payload whose members carry no mlbam. One pass per render; rows
  // whose identity didn't resolve keep the empty placeholder (no layout shift).
  function fillRowPhotos(scope) {
    if (!_faPhotoLegacy || !window.EEPHUS_HUB) return;
    window.EEPHUS_HUB.links().then(L => {
      if (!L) return;
      (scope || document).querySelectorAll(".fa-row-photo[data-photo-key]").forEach(el => {
        const row = (L.byKey || {})[el.dataset.photoKey];
        if (row && row.mlbam) {
          // .fa-row-headshot is 24x24.
          el.innerHTML = `<img class="fa-row-headshot" loading="lazy" src="${faHeadshotURL(row.mlbam, 24)}" alt="" onerror="this.remove()">`;
        }
        el.removeAttribute("data-photo-key");
      });
    });
  }

  // Disclosure badges - the model's weak spots are surfaced, never hidden.
  function thinBadge(m) {
    return m.thinPlatform
      ? ` <span class="fa-thin" title="${esc(m.thinPlatform)}. Low-confidence projection; the market line inherits it.">${window.EephusIco ? window.EephusIco("warn", 12) : ""}</span>` : "";
  }

  function freshnessLine(meta) {
    const src = meta && meta.sources;
    // "data as of" leads even when per-source dates are missing - every
    // module header answers how fresh its numbers are (Open Beta polish).
    const gen = meta && meta.generated_at
      ? `data as of ${esc(String(meta.generated_at))}` : "";
    if (!src || !Object.keys(src).length) {
      return gen ? `<div class="fa-note fa-sources">${gen}</div>` : "";
    }
    const stale = d => (Date.now() - new Date(d + "T00:00:00").getTime()) / 864e5 > 14;
    // Every source checked on one day and none stale: one date, with the
    // per-source list kept in the title.
    const dates = Object.values(src);
    if (dates.every(d => d === dates[0]) && !stale(dates[0])) {
      const each = Object.keys(src).join(", ");
      return `<div class="fa-note fa-sources" title="Sources (${esc(each)}) last checked successfully ${esc(String(dates[0]))}, not the page build date. A quiet market counts as checked; a source that stopped parsing does not.">${meta.generated_at ? `as of ${esc(String(meta.generated_at))} &middot; ` : ""}sources ${esc(String(dates[0]))}</div>`;
    }
    const parts = Object.entries(src).map(([k, d]) =>
      `${k} ${d}${stale(d) ? ` <span class="fa-stale" title="${k} last confirmed ${d}, more than 14 days ago.">${window.EephusIco ? window.EephusIco("warn", 12) : ""} stale</span>` : ""}`);
    return `<div class="fa-note fa-sources" title="Date each source was last checked successfully, not the page build date. A quiet market counts as checked; a source that stopped parsing does not.">${gen ? gen + " &middot; " : ""}sources: ${parts.join(" &middot; ")}</div>`;
  }

  // Share graphics: boards go through the shared EEPHUS_GFX modal, one-subject
  // cards through EEPHUS_HUB.openCard (the shared wrapper; the legacy in-module
  // canvas board renderer was deleted 2026-07-23 - EEPHUS_GFX is always loaded
  // on this page).

  // Board spec for the Generate GFX modal: the constructed class as a column
  // leaderboard (proj years/guarantee, AAV, deal WAR, surplus, verdict).
  function _faBoardSpec(cls, rowsToShow) {
    const top = (rowsToShow || cls.members.filter(m => m.projGuar != null)
      .sort((a, b) => (b.projGuar || 0) - (a.projGuar || 0)))
      .filter(m => m.projGuar != null).slice(0, 50);
    const vc = v => v === "value" ? "pos" : v === "overpay" ? "neg" : "muted";
    const rows = top.map((m, i) => ({ cells: [
      { t: i + 1 },
      { t: m.name, sub: `${m.pos || ""} · ${m.age != null ? Math.floor(m.age) : "?"} · ${m.from || ""}${m.thinPlatform ? " · thin" : ""}` },
      { t: `${m.projYears != null ? m.projYears + "y / " : ""}${money(m.projGuar)}` },
      { t: m.projAav != null ? money(m.projAav) : "-" },
      { t: m.warTotal != null ? m.warTotal.toFixed(1) : "-" },
      { t: m.surplus != null ? formatMetric(m.surplus / 1e6, "surplusM") : "-", c: (m.surplus || 0) >= 0 ? "pos" : "neg" },
      { t: (m.verdict || "-").toUpperCase(), c: vc(m.verdict) },
    ] }));
    const yy = `${cls.class_year - 1}-${String(cls.class_year).slice(2)}`;
    return {
      kind: "board", module: "MLB Free Agency", accentToken: "--accent-green",
      title: `MLB Free Agency · ${yy} Class Board`,
      subtitle: `${cls.n_members} constructed members · ${cls.n_projected} projected · winter $/WAR ${money(cls.dpw_usd)}`,
      url: "eephus.io/fa", filenameBase: `fa-class-board-${yy}`,
      caption: "predicted market vs rational value · ex-ante",
      board: { defaultCount: 25, counts: [10, 25, 50], columns: [
        { label: "#", frac: 0.05 },
        { label: "Player", frac: 0.32 },
        { label: "Yrs / Guar", frac: 0.16 },
        { label: "proj AAV", frac: 0.11 },
        { label: "Deal WAR", frac: 0.10, wideOnly: true },
        { label: "Surplus", frac: 0.14 },
        { label: "Verdict", frac: 0.12, wideOnly: true },
      ], rows },
    };
  }

  // Board spec for the Generate GFX modal when the Signing Tracker view is
  // active, so the graphic tracks the menu you're viewing (each FA view exports
  // its own board). Signed MLB deals ranked by guarantee, with the model's
  // frozen ex-ante prediction and the miss.
  function _faTrackerSpec(cls) {
    const actGuar = m => m.signedGuarNpv ?? m.signedGuar;
    const signed = cls.members
      .filter(m => m.status === "signed" && !m.signedMilb && m.signedGuar != null)
      .sort((a, b) => (b.signedGuar || 0) - (a.signedGuar || 0)).slice(0, 50);
    const rows = signed.map((m, i) => {
      const dGuar = m.projGuar != null ? (actGuar(m) - m.projGuar) / 1e6 : null;
      return { cells: [
        { t: i + 1 },
        { t: m.name, sub: `${m.pos || ""} · ${m.from || ""} → ${m.signedTo || ""}` },
        { t: `${m.signedYears ?? "?"}y / ${money(m.signedGuar)}`, c: "accent" },
        { t: m.projGuar != null ? `${m.projYears}y / ${money(m.projGuar)}` : "-" },
        { t: dGuar != null ? formatMetric(dGuar, "surplusM") : "-" },
      ] };
    });
    const yy = `${cls.class_year - 1}-${String(cls.class_year).slice(2)}`;
    const spent = signed.reduce((s, m) => s + (m.signedGuar || 0), 0);
    return {
      kind: "board", module: "MLB Free Agency", accentToken: "--accent-green",
      title: `MLB Free Agency · ${yy} Signing Tracker`,
      subtitle: `${signed.length} MLB deals · ${money(spent)} guaranteed`,
      url: "eephus.io/fa", filenameBase: `fa-signing-tracker-${yy}`,
      caption: "actual deal vs the model's frozen ex-ante prediction (NPV basis)",
      board: { defaultCount: 25, counts: [10, 25, 50], columns: [
        { label: "#", frac: 0.05 },
        { label: "Player", frac: 0.40 },
        { label: "Actual", frac: 0.18 },
        { label: "Predicted", frac: 0.19, wideOnly: true },
        { label: "Δ Guar", frac: 0.16 },
      ], rows },
    };
  }

  // Board spec for the Generate GFX modal when the Team Fits view is active:
  // the selected club's fit leaders (fit composite + its component scores +
  // how many near-ETA prospects / MLB incumbents block the slot). Takes the
  // already-sorted per-team list renderFits builds, so the graphic matches the
  // on-screen ranking exactly.
  function _faFitsBoardSpec(cls, meta, team, list) {
    const yy = `${cls.class_year - 1}-${String(cls.class_year).slice(2)}`;
    const t = (meta && meta.teams && meta.teams[team]) || {};
    const vc = v => v === "value" ? "pos" : v === "overpay" ? "neg" : "muted";
    const sc = v => v != null ? Number(v).toFixed(2) : "-";
    const top = (list || []).slice(0, 50);
    const rows = top.map(({ m, f }, i) => ({ cells: [
      { t: i + 1 },
      { t: m.name, sub: `${m.pos || ""} · ${m.age != null ? Math.floor(m.age) : "?"}` },
      { t: f.fit != null ? f.fit.toFixed(2) : "-", c: "accent" },
      { t: sc(f.need) },
      { t: sc(f.window) },
      { t: sc(f.afford) },
      { t: sc(f.park) },
      { t: sc(f.behavior) },
      { t: (f.blockedBy && f.blockedBy.length) ? String(f.blockedBy.length) : "0", c: (f.blockedBy && f.blockedBy.length) ? "neg" : "muted" },
      { t: (m.verdict || "-").toUpperCase(), c: vc(m.verdict) },
    ] }));
    return {
      kind: "board", module: "MLB Free Agency", accentToken: "--accent-green",
      title: `MLB Free Agency · ${team} Team Fits`,
      subtitle: `${yy} class · ${top.length} scored fits · CBT payroll ${money(t.taxPayroll ?? t.committed)}${t.space != null ? ` · tax space ${formatMetric(t.space / 1e6, "surplusM")}` : ""}`,
      url: "eephus.io/fa", filenameBase: `fa-team-fits-${team}-${yy}`,
      caption: "team fit composite · blocked = slot already held",
      board: { defaultCount: 25, counts: [10, 25, 50], legend: "Fit = need/window/afford/park/behavior composite", columns: [
        { label: "#", frac: 0.05 },
        { label: "Player", frac: 0.28 },
        { label: "Fit", frac: 0.10 },
        { label: "Need", frac: 0.08 },
        { label: "Window", frac: 0.09 },
        { label: "Afford", frac: 0.09 },
        { label: "Park", frac: 0.07, wideOnly: true },
        { label: "Behavior", frac: 0.09, wideOnly: true },
        { label: "Blocked", frac: 0.08 },
        { label: "Verdict", frac: 0.07, wideOnly: true },
      ], rows },
    };
  }

  // Board spec for the Generate GFX modal when the Archive view is active: the
  // selected winter's signings ranked by realized surplus-to-date, with the
  // realized WAR delivered so far as the accent column (the winter graded by
  // what has actually happened, not projections).
  function _faArchiveBoardSpec(w) {
    const yy = `${w.year - 1}-${String(w.year).slice(2)}`;
    const signings = (w.signings || []).slice().sort((a, b) => {
      const av = a.surplusTd, bv = b.surplusTd;
      if (av == null && bv == null) return 0;
      if (av == null) return 1;
      if (bv == null) return -1;
      return bv - av;
    }).slice(0, 50);
    const rows = signings.map((s, i) => ({ cells: [
      { t: i + 1 },
      { t: s.name, sub: `${s.pos || ""} · ${s.from || "?"} → ${s.to || "?"}` },
      { t: s.milb ? "MiLB deal" : `${s.years ?? "?"}y / ${money(s.guar)}` },
      { t: s.warTd != null ? formatMetric(s.warTd, "war") : "-", c: "accent" },
      { t: s.surplusTd != null ? formatMetric(s.surplusTd / 1e6, "surplusM") : "-", c: s.surplusTd == null ? "muted" : (s.surplusTd >= 0 ? "pos" : "neg") },
      { t: s.done ? "complete" : (s.warTd != null ? "running" : "-"), c: "muted" },
    ] }));
    return {
      kind: "board", module: "MLB Free Agency", accentToken: "--accent-green",
      title: `MLB Free Agency · ${yy} Archive`,
      subtitle: `${w.n} signings · ${money(w.spend_usd)} guaranteed · implied $/WAR ${money(w.dpw_usd)}`,
      url: "eephus.io/fa", filenameBase: `fa-archive-${yy}`,
      caption: `realized ${realizedWar()} and surplus to date`,
      board: { defaultCount: 25, counts: [10, 25, 50], legend: "realized through today", columns: [
        { label: "#", frac: 0.05 },
        { label: "Player", frac: 0.34 },
        { label: "Yrs / Guar", frac: 0.18 },
        { label: "WAR-to-date", frac: 0.14 },
        { label: "Surplus", frac: 0.15 },
        { label: "Status", frac: 0.14, wideOnly: true },
      ], rows },
    };
  }

  // Blocked-by chips: WHO and WHAT KIND ('prospect' = PROSPX near-ETA,
  // 'mlb' = a contracted incumbent already producing at the slot).
  function blockedText(blockedBy) {
    if (!blockedBy || !blockedBy.length) return "";
    return blockedBy.map(b => `${b.n} (${b.t === "mlb" ? "MLB incumbent" : "prospect"})`).join(", ");
  }

  // FA type: UFA (contract expires - locked into the class) vs the OPTION
  // family (club / player / mutual / conditional / opt-out), whose class
  // membership is PROBABILISTIC until the option resolves. The colored pill +
  // row accent make options scannable apart from the UFAs; the Type filter
  // isolates either group.
  const OPT_LABEL = {
    ufa: "UFA", club_option: "Club opt", player_option: "Player opt",
    mutual_option: "Mutual opt", conditional_club_option: "Cond. club opt",
    conditional_player_option: "Cond. player opt", opt_out: "Opt-out",
  };
  function isOption(m) { return (m.type || "ufa") !== "ufa"; }
  function typeTag(m) {
    const t = m.type || "ufa";
    const lbl = OPT_LABEL[t] || t.replace(/_/g, " ");
    const opt = isOption(m);
    const tip = opt
      ? "Option or opt-out: membership is probabilistic until it resolves"
      : "UFA: contract expires; locked into the class";
    return `<span class="fa-type ${opt ? "fa-type-opt" : "fa-type-ufa"}" title="${tip}">${lbl}</span>`;
  }
  function posHead(m) {
    return String(m.pos || "").toUpperCase().split("/")[0];
  }
  function posGroup(m) {
    const head = posHead(m);
    return ["SP", "LHP", "RHP", "P"].includes(head) ? "SP"
      : ["RP", "CL"].includes(head) ? "RP" : head === "C" ? "C"
      : ["1B", "2B", "3B", "SS"].includes(head) ? "IF"
      : ["LF", "CF", "RF", "OF"].includes(head) ? "OF" : "DH";
  }
  // Filter chips accept BOTH the coarse roll-ups (IF / OF / SP / RP) and a specific
  // position (1B / 2B / 3B / SS / LF / CF / RF). The class data is already granular -
  // pos carries 1B/2B/3B/SS/LF/CF/RF/C/DH/SP/RP - so a specific chip matches the raw
  // head position while a roll-up chip keeps the grouped behaviour.
  const POS_ROLLUPS = new Set(["C", "IF", "OF", "SP", "RP", "DH"]);
  function posMatches(m, sel) {
    return POS_ROLLUPS.has(sel) ? posGroup(m) === sel : posHead(m) === sel;
  }

  // The board's default order is the predicted guarantee: the biggest deals
  // first, which is what the printed rank numbers mean. # (rank) resolves to
  // the same key, so the two agree.
  const boardState = { sort: "projGuar", dir: -1, type: "all", pos: "all", verdict: "all", hand: "all" };
  let faFiltersOpen = false;   // the phone filter drawer

  // ---- board sorting ---------------------------------------------------------
  // Every key the retired card head and "Sort tape" carried keeps working, plus
  // dealPlus and prevAav, which the table prints for the first time. Anything
  // else arriving on #sort= falls back to the default instead of sorting every
  // row as a tie.
  const FA_SORT_KEYS = ["rank", "name", "status", "verdict", "projAav", "projYears",
    "projGuar", "surplus", "dealPlus", "rational", "warY1", "warTotal",
    "warCvar10", "pAnyStar", "age", "prevAav"];
  // Every key the picker offers. Only `rank` is dropped: it is the default order
  // under another name and has its own column. warCvar10, pAnyStar and prevAav
  // have NO column at any width, so the picker is the only way to reach them and
  // it is therefore never hidden.
  // IL days, last three seasons (wiring W01, Q9_22c): a key only while the MLB
  // events feed is live, so with the flag off the board is unchanged.
  if (ilLive()) FA_SORT_KEYS.push("ilDays");
  const FA_PICK_KEYS = FA_SORT_KEYS.filter(k => k !== "rank");
  // First click ascending: A-Z, youngest, and the status ladder from locked.
  const FA_ASC_FIRST = ["name", "age", "status"];
  function faNaturalDir(k) { return FA_ASC_FIRST.indexOf(k) >= 0 ? 1 : -1; }
  // The value a row sorts on, or null when it has none. Null is not a number to
  // compare: it sorts LAST in both directions (faSortRows below). The card
  // comparator substituted a huge negative sentinel instead, so every ascending
  // sort opened on the four unprojected rows.
  function faSortVal(m, k) {
    if (k === "rank") return m.projGuar ?? null;
    if (k === "ilDays") { const x = ilOf(m); return x ? x.total : null; }
    if (k === "name") return String(m.name || "");
    if (k === "status" || k === "verdict") return String(m[k] || "") || null;
    return m[k] ?? null;
  }
  function faSortRows(list) {
    const k = boardState.sort, dir = boardState.dir;
    const byName = (a, b) => a.n.localeCompare(b.n, undefined, { sensitivity: "base" });
    const keyed = list.map(m => ({ m, v: faSortVal(m, k), g: m.projGuar ?? -1, n: String(m.name || "") }));
    keyed.sort((a, b) => {
      if (a.v == null || b.v == null) {
        if (a.v == null && b.v == null) return (b.g - a.g) || byName(a, b);
        return a.v == null ? 1 : -1;            // missing values last, either direction
      }
      const c = typeof a.v === "string"
        ? a.v.localeCompare(b.v, undefined, { sensitivity: "base" })
        : (a.v > b.v ? 1 : a.v < b.v ? -1 : 0);
      if (c) return dir * c;
      return (b.g - a.g) || byName(a, b);       // ties keep the guarantee order
    });
    return keyed.map(x => x.m);
  }
  const FA_SORT_LBL = {
    rank: "Guarantee", name: "Name", status: "Status", verdict: "Verdict",
    projAav: "proj AAV", projYears: "Years", projGuar: "Guarantee",
    surplus: "Surplus", dealPlus: "Deal+", rational: "Rational value",
    warY1: "WAR y1", warTotal: "Deal WAR", warCvar10: "Downside WAR",
    pAnyStar: "Star odds", age: "Age", prevAav: "Prior AAV",
    ilDays: "IL days, last 3 seasons",
  };

  // ---- IL days, last three seasons (wiring W01, Q9_22c) ----------------------
  // Read only while the page shell says the MLB events feed is live
  // (data-mlb-events on #fa-rows, written from mlb_events.MLB_EVENTS_LIVE): the
  // column, its sort key and the detail line read il_recent from the events
  // index, in-season IL days per season (Apr 1 to Oct 1, ended by the next IL
  // move). A member
  // resolves to an MLBAM id through its own mlbam or the player links map.
  // Descriptive only: no availability forecast rides on it.
  let IL = null;            // {seasons, days} once loaded, false if it failed
  let IL_LINKS = null;
  function ilLive() {
    const r = document.getElementById("fa-rows");
    return !!(r && r.dataset.mlbEvents === "live");
  }
  function ilOn() { return ilLive() && !!IL; }
  function loadIl(cls) {
    if (!ilLive()) return Promise.resolve(null);
    const needLinks = !IL_LINKS && cls && (cls.members || []).some(m => !m.mlbam) && window.EEPHUS_HUB;
    const links = needLinks
      ? window.EEPHUS_HUB.links().then(L => { IL_LINKS = L || null; }, () => {})
      : Promise.resolve();
    const idx = IL !== null ? Promise.resolve()
      : fetch("/data/mlb_events/index.json", { cache: "no-cache" })
        .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
        .then(j => { IL = (j && j.il_recent && Array.isArray(j.il_recent.seasons)) ? j.il_recent : false; })
        .catch(() => { IL = false; });
    return Promise.all([idx, links]).then(() => IL);
  }
  function ilMlbam(m) {
    if (m.mlbam) return m.mlbam;
    const row = IL_LINKS && (IL_LINKS.byKey || {})[m.key];
    return row && row.mlbam ? row.mlbam : null;
  }
  // {per: [days by season], total} or null when the member has no MLBAM id.
  // A resolved player missing from il_recent had no IL day in the window: the
  // index carries every MLB-club IL move.
  function ilOf(m) {
    if (!IL) return null;
    const id = ilMlbam(m);
    if (!id) return null;
    const per = (IL.days || {})[String(id)] || IL.seasons.map(() => 0);
    return { per, total: per.reduce((a, b) => a + b, 0) };
  }
  function ilSplit(x) {
    return IL.seasons.map((y, i) => `${y}: ${x.per[i]}`).join(", ");
  }
  function ilCell(m) {
    const x = ilOf(m);
    if (!x) return EM_DASH;
    return `<span title="In-season IL days by season (${esc(ilSplit(x))})">${x.total}</span>`;
  }

  // Which "biggest misses" category the Model Accountability table is showing.
  let modelMissTab = "guar";   // guar | years | aav

  // ---- Class Board: ONE TABLE (2026-09-16, owner ask B) ----------------------
  // The card grid put 2 rows above the fold at 1440 and 0 on a phone. This is
  // the /projections/ Players table applied to the class: one fixed-layout
  // <table>, a header that sticks to the viewport, every key sortable from its
  // own column, and columns that fold by BOARD width into the sub line and the
  // per-row detail line rather than ellipsizing a name.

  // Bands are composed ONCE and read by three places: the [data-band] cell's
  // aria-label (which openBand shows verbatim), the cell title, and the detail
  // line. The aavWild disclosure (the bands are a flat ratio, not a per-tier
  // fit, so the top of the market gets a P90 no contract has reached) cannot
  // drift out of sync with the number it warns about. The surplus sentence is
  // NOT rebuilt here: surplusBandText above is the one composer, so the cell
  // and the detail line read the same string on every row.
  function faBands(m) {
    const wild = m.projAav > 0 && m.projAavP90 != null && m.projAavP90 > m.projAav * 2.5;
    return {
      wild,
      aav: `Predicted average annual value ${money(m.projAav)}. `
        + `P10 to P90 ${money(m.projAavP10)} to ${money(m.projAavP90)}.`
        + (wild ? " The band is a flat ratio, not a per-tier fit, so the"
                  + " upper end is too wide at the top of the market." : ""),
      yrs: `Predicted term ${m.projYears ?? "?"} years. `
        + `P10 to P90 ${m.projYearsP10 ?? "?"} to ${m.projYearsP90 ?? "?"} years.`,
      guar: `Predicted total guarantee ${money(m.projGuar)}. `
        + `P10 to P90 ${money(m.projGuarP10)} to ${money(m.projGuarP90)}.`,
      surplus: surplusBandText(m.surplus, m.surplusP10, m.surplusP90),
    };
  }
  // A tap-to-open band cell. Same contract as the card had: tabindex, aria-label
  // read by openBand, dotted underline, and a click that does not leave the row.
  function faBandCell(text, label) {
    if (text == null) return EM_DASH;
    return `<span data-band tabindex="0" aria-label="${esc(label)}" title="${esc(label)}">${text}</span>`;
  }

  // Status, compact, and LEADING WITH THE WORD. The card spent the second
  // widest track on the string "UFA" for 165 of 236 rows; a cell that printed
  // only a price and a percentage would instead have taken its meaning from the
  // type pill 300px away in the Player cell. So the cell says which option it
  // is, the price rides with it, and P(enter) moves to the title, the sub line
  // and the detail line. Every title is the retired statusChip sentence
  // verbatim, with the P(enter) sentence appended for the option family, so no
  // prose is lost.
  const FA_OPT_SHORT = {
    club_option: "CLUB OPT", player_option: "PLYR OPT", mutual_option: "MUT OPT",
    conditional_club_option: "COND CLUB", conditional_player_option: "COND PLYR",
    opt_out: "OPT OUT",
  };
  function faStatus(m) {
    if (m.status === "signed") {
      const terms = m.signedMilb ? "MiLB" : `${m.signedYears ?? "?"}y ${money(m.signedGuar)}`;
      const to = esc(m.signedTo || "");
      return { short: `${to} ${terms}`, cls: "fa-st-signed",
        sub: `<span class="fa-sr-sm">SIGNED </span>${to} ${terms}`,
        long: `SIGNED ${to} ${terms}`,
        tip: `Signed${m.signedDate ? ", first seen " + m.signedDate + " (pipeline observation date)" : ""}.` };
    }
    if (m.status === "option_exercised") {
      return { short: "EXERCISED", cls: "fa-st-off", sub: "EXERCISED", long: "option exercised",
        tip: "Option exercised; never reached the market (first-seen heuristic)." };
    }
    // TWO SOURCES, ONE PLAYER. Class membership is scraped from Spotrac's
    // free-agents-available list and never consults the arbitration board, so a
    // member can be published here as a free agent for this class while
    // mlb_projections prices him club-controlled past it on a PROJECTED
    // arbitration season. fa_export stamps `ctrlFlag` on exactly those rows.
    // This does not move membership, which is a data-sourcing question; it stops
    // the site publishing two confident and incompatible answers in silence.
    const ctrlNote = m.ctrlFlag
      ? ` Spotrac lists him as a free agent for this class; the arbitration board prices him under club control through ${m.ctrlThru}. The two sources disagree.`
      : "";
    if (m.status === "locked") {
      return { short: `UFA${m.ctrlFlag ? " \u00b7 ?" : ""}`, cls: `fa-st-ufa${m.ctrlFlag ? " fa-st-ctrlflag" : ""}`,
        sub: `UFA${m.ctrlFlag ? " \u00b7 ?" : ""}`, long: "UFA",
        tip: "Contract expires; locked into the class"
          + (m.ctrlFlag ? ", unless the club control window on the projections board is right." : ".")
          + ctrlNote };
    }
    const type = String(m.type || "");
    const word = FA_OPT_SHORT[type] || esc(type.replace(/_/g, " ").toUpperCase()) || "OPTION";
    const words = esc(type.replace(/_/g, " ")) || "option";
    const pct = m.enterProb != null ? `${(m.enterProb * 100).toFixed(0)}%` : "";
    const price = m.optPrice ? `$${(m.optPrice / 1e6).toFixed(1)}M` : "";
    const src = m.enterProbSrc && m.enterProbSrc.indexOf("band_priced") === 0
      ? "P(enter) from the option price against the predicted AAV band (v2)."
      : "P(enter) from the v1 heuristic (mutual and conditional options keep explicit priors).";
    return {
      short: (price ? `${word} ${price}` : word) + (m.ctrlFlag ? " \u00b7 ?" : ""),
      cls: `fa-st-opt${m.ctrlFlag ? " fa-st-ctrlflag" : ""}`,
      sub: `${word}${price ? " " + price : ""}${pct ? " &middot; " + pct : ""}`,
      long: `${words}${price ? " " + price : ""}${pct ? " &middot; P(enter) " + pct : ""}`,
      tip: `Option pending: membership is probabilistic until it resolves. ${src}`
        + (pct ? ` P(enter) ${pct} is the probability the row reaches the market.` : "")
        + ctrlNote,
    };
  }
  // Deal+ is the number every verdict is cut on and the card printed it nowhere
  // but a tooltip. Its bands are the per-group terciles served in
  // fa_meta.gate2.verdict_edges (never the 93/107/120 z ruler), read off the
  // artifact by _faVerdictBand so a re-cut cannot leave the sentence stale. The
  // column itself carries no colour and no band class: the only banding a
  // reader sees on this board is the Verdict pill.
  function faDealPlusTip(m) {
    const b = _faVerdictBand(m.pos);
    return `Rational value as a percentage of the predicted price; 100 means the`
      + ` model and the market agree.` + (b ? ` Overpay below ${b.lo}, value at or above ${b.hi} (${b.basis} terciles).` : "");
  }

  // Row detail line: every fact a folded column carried, plus the ones no column
  // carries (the three P10-P90 bands with their disclosure, the option
  // decomposition, the prior deal, the comps, the top team fits, the thin
  // platform reason and the unprojected reason - the last two were carried in
  // the payload and rendered nowhere). Emitted only for open rows.
  const FA_OPEN = new Set();
  function faDetailRow(m, cls) {
    const b = faBands(m);
    const g = (label, body, gl) => `<span class="fa-dt-g"><b${gl ? ` data-gl="${gl}"` : ""}>${label}</b> ${body}</span>`;
    const parts = [];
    const st = faStatus(m);
    parts.push(g("Status", `${st.long}`));
    if (m.noProj) {
      const why = (cls.unprojected_reason_text || {})[m.noProj];
      parts.push(g("Not projected", esc(why || String(m.noProj).replace(/_/g, " "))));
    }
    if (m.projYears != null) parts.push(g("Term", `${m.projYears}y &middot; P10-P90 ${m.projYearsP10 ?? "?"} to ${m.projYearsP90 ?? "?"}`, "m_years"));
    if (m.projGuar != null) parts.push(g("Guarantee", `${money(m.projGuar)} &middot; P10-P90 ${money(m.projGuarP10)} to ${money(m.projGuarP90)}`, "m_guarantee"));
    if (m.projAav != null) parts.push(g("AAV", `${money(m.projAav)} &middot; P10-P90 ${money(m.projAavP10)} to ${money(m.projAavP90)}${b.wild ? ". The band is a flat ratio, not a per-tier fit, so the upper end is too wide at the top of the market" : ""}`, "m_aav"));
    if (m.rational != null) parts.push(g("Rational value", money(m.rational), "rational_value"));
    // surplusBandParts is the only formatter of a surplus number and b.surplus is
    // the only composer of its sentence, so this line cannot drift from the cell.
    // A row with a surplus and no band prints the number alone rather than the
    // "$0.0M" end a `?? 0` used to invent.
    const sp = surplusBandParts(m.surplus, m.surplusP10, m.surplusP90);
    if (sp != null) parts.push(g("Surplus", b.surplus == null ? sp.val
      : `${sp.val} &middot; P10-P90 ${sp.lo} to ${sp.hi}`, "contract_surplus"));
    if (m.dealPlus != null) parts.push(g("Deal+", `${m.dealPlus}`, "deal_plus"));
    const war = [];
    if (m.warY1 != null) war.push(`y1 ${formatMetric(m.warY1, "war")}`);
    if (m.warTotal != null) war.push(`deal ${formatMetric(m.warTotal, "war")}`);
    if (m.warCvar10 != null) war.push(`<span data-gl="downside_war" title="Mean of the worst 10% of outcome paths (CVaR), not the P10">downside WAR</span> ${formatMetric(m.warCvar10, "war")}`);
    if (war.length) parts.push(g("eWAR", war.join(" &middot; "), "ewar"));
    if (m.pAnyStar != null) parts.push(g("Star odds", `${(m.pAnyStar * 100).toFixed(0)}%`, "star_odds"));
    if (m.optKind) {
      parts.push(g("Option", `${esc(String(m.optKind))}${m.optHeldBy ? " / " + esc(String(m.optHeldBy)) : ""}`
        + (m.optPrice ? ` &middot; ${money(m.optPrice)}` : "")
        + (m.enterProb != null ? ` &middot; <span data-gl="p_enter">P(enter)</span> ${(m.enterProb * 100).toFixed(0)}%` : "")
        + (m.optValue != null ? ` &middot; modelled value ${money(m.optValue)}` : "")));
    }
    if (m.prevAav != null) parts.push(g("Prior deal", `${money(m.prevAav)} AAV`));
    const il = ilOn() ? ilOf(m) : null;
    if (il) parts.push(g("IL days", `${il.total} &middot; ${esc(ilSplit(il))}`, "il_days_3y"));
    if (m.thinPlatform) parts.push(g("Thin platform", `${esc(m.thinPlatform)}. Low-confidence projection; the market line inherits it.`, "thin_platform"));
    if ((m.comps || []).length) {
      parts.push(g("Comps", m.comps.slice(0, 3).map(c =>
        `${esc(c.name)} ${c.yr}${c.to ? " " + esc(c.to) : ""} ${c.years ?? "?"}y ${money(c.guar)}`).join(" &middot; ")));
    }
    if ((m.fits || []).length) {
      parts.push(g("Top fits", m.fits.slice(0, 3).map(f =>
        `<a class="fa-player-link" href="#${faHash()}view=fits&team=${encodeURIComponent(f.org)}">${esc(f.org)}</a> ${(f.fit ?? 0).toFixed(2)}`).join(" &middot; "), "team_fit"));
    }
    // Every href on this board is faHash()-prefixed: the retired whole-card
    // click handler was not, so a click on a future-class row dropped class=
    // and re-read the current class.
    parts.push(`<span class="fa-dt-g"><a class="fa-player-link" href="#${faHash()}player=`
      + `${encodeURIComponent(m.key || "")}">Full card</a></span>`);
    // One pad per foldable column, each carrying that column's fold class, so
    // the row paints exactly as many cells as the header does at every width. A
    // colspan past the painted columns adds phantom columns to a fixed-layout
    // table and crushes the Player column.
    const pad = c => `<td class="${c} fa-dt-pad" aria-hidden="true"></td>`;
    const tail = ["fc-sur", "fc-dp", "fc-rat", "fc-w1", "fc-wt", "fc-age"]
      .concat(ilOn() ? ["fc-il"] : [], ["fc-st"]);
    return `<tr class="fa-detail" id="fad-${esc(m.key)}" data-export-skip>${pad("fc-rank")}`
      + `<td colspan="5" class="fa-dt-cell"><div class="fa-dt">${parts.join("")}</div></td>`
      + tail.map(pad).join("") + `</tr>`;
  }

  function faRowHtml(m, i) {
    const b = faBands(m);
    const st = faStatus(m);
    const open = FA_OPEN.has(m.key);
    const trCls = [
      (m.projGuar == null || m.status === "option_exercised") ? "fa-dim" : "",
      isOption(m) ? "fa-row-opt" : "",
    ].filter(Boolean).join(" ");
    const xp = `<button type="button" class="fa-xp-btn" data-xp-key="${esc(m.key)}" aria-expanded="${open}"`
      + `${open ? ` aria-controls="fad-${esc(m.key)}"` : ""} aria-label="Details: ${esc(m.name)}" title="Details">&#9662;</button>`;
    // Sub line: identity that has no column, then the facts whose columns fold
    // at narrow widths (CSS reveals them only then, each behind its own dot).
    const sub = `<span class="fa-pl-sub"><span class="fa-sub-id">${esc(m.pos || "")}`
      + `${m.from ? ` &middot; ${clubTag(m.from)}` : ""}${handOf(m) ? " &middot; " + handShort(m) : ""}</span>`
      + `<span class="fa-sub-age" title="Age in the free-agent season"><span class="fa-sr-sm">age </span>${m.age != null ? m.age.toFixed(1) : "?"}</span>`
      + `<span class="fa-sub-st ${st.cls}" title="${esc(st.tip)}">${st.sub}</span></span>`;
    const dp = m.dealPlus != null
      ? `<span title="${esc(faDealPlusTip(m))}">${m.dealPlus}</span>` : EM_DASH;
    return `<tr data-key="${esc(m.key)}"${trCls ? ` class="${trCls}"` : ""}>`
      + `<td class="fc-rank">${i + 1}</td>`
      + `<th scope="row" class="fc-player" data-export-text="${esc(m.name)}"><div class="fa-pl">${rowPhoto(m)}`
      + `<a class="fa-player-link mlb-name fa-pl-name" href="#${faHash()}player=${encodeURIComponent(m.key || "")}" title="${esc(m.name)}">${esc(m.name)}</a>`
      + `<span class="fa-pl-tags">${thinBadge(m)}${typeTag(m)}</span>${xp}${sub}</div></th>`
      + `<td class="fc-csv" hidden>${esc(m.pos || "")}</td><td class="fc-csv" hidden>${esc(m.from || "")}</td>`
      + `<td class="fc-vd">${verdictChip(m)}</td>`
      + `<td class="fc-aav">${faBandCell(m.projAav == null ? null : money(m.projAav), b.aav)}</td>`
      + `<td class="fc-yrs">${m.projYears == null ? EM_DASH : `<span title="${esc(b.yrs)}">${m.projYears}y</span>`}</td>`
      + `<td class="fc-guar">${faBandCell(m.projGuar == null ? null : money(m.projGuar), b.guar)}</td>`
      + `<td class="fc-sur">${surplusSpan(m.surplus, m.surplusP10, m.surplusP90)}</td>`
      + `<td class="fc-dp">${dp}</td>`
      + `<td class="fc-rat">${m.rational != null ? money(m.rational) : EM_DASH}</td>`
      + `<td class="fc-w1">${m.warY1 != null ? formatMetric(m.warY1, "war") : EM_DASH}</td>`
      + `<td class="fc-wt">${m.warTotal != null ? formatMetric(m.warTotal, "war") : EM_DASH}</td>`
      + `<td class="fc-age">${m.age != null ? Math.floor(m.age) : EM_DASH}</td>`
      + (ilOn() ? `<td class="fc-il">${ilCell(m)}</td>` : "")
      + `<td class="fc-st"><span class="fa-st ${st.cls}" title="${esc(st.tip)}">${st.short}</span></td>`
      + `</tr>`;
  }

  function renderBoard(rows, cls) {
    let members = cls.members.slice();
    if (boardState.type === "ufa") members = members.filter(m => !isOption(m));
    else if (boardState.type === "options") members = members.filter(isOption);
    if (boardState.pos !== "all") members = members.filter(m => posMatches(m, boardState.pos));
    if (boardState.verdict !== "all") members = members.filter(m => m.verdict === boardState.verdict);
    if (boardState.hand !== "all") members = members.filter(m => handOf(m) === boardState.hand);
    members = faSortRows(members);
    const sortKey = boardState.sort;
    const arrow = boardState.dir < 0 ? "&#9662;" : "&#9652;";

    // A real <th scope="col"> carrying aria-sort (valid on a columnheader)
    // around a native <button>: Enter and Space with no keydown shim, one tab
    // stop, and no glossary hook nested inside a control. data-export-text
    // keeps the arrow and the phone short forms out of the CSV.
    const th = (key, label, cname, title, exportText) => {
      const on = sortKey === key;
      const aria = on ? (boardState.dir < 0 ? "descending" : "ascending") : "none";
      return `<th scope="col" class="${cname}" aria-sort="${aria}" data-export-text="${esc(exportText)}">`
        + `<button type="button" class="fa-sort" data-fsort="${key}" title="${esc(title)}">${label}`
        + `<span class="fa-sort-ind" aria-hidden="true">${on ? arrow : ""}</span></button></th>`;
    };
    const head = `<thead><tr>`
      + th("rank", "#", "fc-rank", "Board position under the current sort", "#")
      + th("name", "Player", "fc-player", "Sort by name", "Player")
      + `<th class="fc-csv" hidden data-export-text="Pos"></th><th class="fc-csv" hidden data-export-text="Org"></th>`
      + th("verdict", "Verdict", "fc-vd", "Deal+ banded within the player's position group", "Verdict")
      + th("projAav", "AAV", "fc-aav", "Predicted average annual value. Tap a cell for the P10-P90 band.", "proj AAV")
      + th("projYears", "Yrs", "fc-yrs", "Predicted contract length; the P10-P90 term band is in the row details", "Yrs")
      + th("projGuar", "Guar", "fc-guar", "Predicted total guarantee. Tap a cell for the P10-P90 band.", "Guarantee")
      + th("surplus", "Surplus", "fc-sur", "Rational value minus predicted price. Tap a cell for the P10-P90 range.", "Surplus")
      + th("dealPlus", "Deal+", "fc-dp", "Rational value as a percentage of the predicted price; 100 means the model and the market agree", "Deal+")
      + th("rational", "Rational", "fc-rat", "Convex-priced NPV of the projected production", "Rational value")
      + th("warY1", `WAR<span class="fa-th-unit">y1</span>`, "fc-w1", "Projected year-1 WAR (fWAR basis, the training label)", "WAR y1")
      + th("warTotal", `WAR<span class="fa-th-unit">deal</span>`, "fc-wt", "Projected WAR over the predicted term (fWAR basis)", "Deal WAR")
      + th("age", "Age", "fc-age", "Age in the free-agent season", "Age")
      + (ilOn() ? th("ilDays", `IL<span class="fa-th-unit">3y</span>`, "fc-il",
        `IL days, last three seasons: in-season days on the injured list, ${IL.seasons[0]} to ${IL.seasons[IL.seasons.length - 1]}, summed`,
        "IL days 3y") : "")
      + th("status", "Status", "fc-st", "Market status: UFA, a pending option with its price, or the signed deal", "Status")
      + `</tr></thead>`;
    const body = members.map((m, i) => faRowHtml(m, i) + (FA_OPEN.has(m.key) ? faDetailRow(m, cls) : "")).join("");

    const gl = `<span data-gl="war">WAR</span> (fWAR basis) &middot; <span data-gl="rational_value">rational</span>`
      + ` &middot; <span data-gl="contract_surplus">surplus</span> &middot; <span data-gl="deal_plus">Deal+</span>`;
    const headEyebrow = `<div class="newsprint-eyebrow" style="margin-top:4px;">
      <span class="newsprint-eyebrow-label">${cls.class_year - 1}-${String(cls.class_year).slice(2)} Class Board</span>
      <span class="newsprint-eyebrow-meta">${members.length} of ${cls.members.length} &middot; winter <span data-gl="winter_dpw">$/WAR</span> (ex-ante) ${money(cls.dpw_usd)}, ${cls.pricing_basis ? `each season at its own level on the one written path (escalator ${(cls.pricing_basis.g_ref * 100).toFixed(2)}%/yr, discounted at ${(cls.pricing_basis.nominal_rate * 100).toFixed(2)}%)` : `<span title="Escalating ${((cls.dpw_infl ?? 0.05) * 100).toFixed(1)}% a year">+${((cls.dpw_infl ?? 0.05) * 100).toFixed(1)}%/yr</span>`} &middot; ${gl}</span>
    </div>`;
    const nUfa = cls.members.filter(m => !isOption(m)).length;
    const nOpt = cls.members.length - nUfa;
    const fchip = (group, val, label, on) =>
      `<button class="chip fa-fchip${on ? " active" : ""}" data-ffilter="${group}" data-fval="${val}">${label}</button>`;
    const POS_OPTS = [["all", "All"], ["C", "C"], ["IF", "IF"], ["OF", "OF"], ["SP", "SP"], ["RP", "RP"], ["DH", "DH"],
      ["1B", "1B"], ["2B", "2B"], ["3B", "3B"], ["SS", "SS"], ["LF", "LF"], ["CF", "CF"], ["RF", "RF"]];
    // The sort control is ALWAYS rendered: three keys (downside WAR, star odds,
    // prior AAV) have no column at any width, so a control that only appeared
    // once a column folded would leave them reachable by hand-typing #sort= and
    // nothing else. It sits on its own row rather than inside the filter bar:
    // measured 2026-09-16, the bar's 15 chips plus the position select already
    // run 870px of a 1088px inner width at 1440, so a 253px picker wrapped the
    // bar to two lines at 1440, 1280, 1100 and 1024. The own row costs 23px at
    // every width instead, which is the pre-registered fallback.
    const dirWord = sortKey === "name" ? (boardState.dir > 0 ? "A-Z" : "Z-A")
      : (boardState.dir < 0 ? "high first" : "low first");
    // Belt and braces: an active sort somehow outside the list is appended, so
    // the picker always shows what the board is actually doing.
    const extraOpt = FA_PICK_KEYS.indexOf(sortKey) >= 0 ? ""
      : `<option value="${esc(sortKey)}" selected>${esc(FA_SORT_LBL[sortKey] || sortKey)}</option>`;
    // One control row: sort, the phone filter drawer toggle, the share chip.
    const nFilt = ["type", "pos", "verdict", "hand"].filter(k => boardState[k] !== "all").length;
    const tools = `<div class="fa-board-tools"><span class="fa-sort-pick"><label for="fa-sort-sel">Sort</label>
      <select id="fa-sort-sel" class="fa-select">${FA_PICK_KEYS.map(k =>
        `<option value="${k}"${sortKey === k ? " selected" : ""}>${esc(FA_SORT_LBL[k] || k)}</option>`).join("")}${extraOpt}</select>
      <button type="button" class="chip" id="fa-sort-dir" aria-label="Reverse sort">${arrow} ${dirWord}</button></span>
      <button type="button" class="chip fa-filter-toggle" id="fa-filter-toggle" aria-controls="fa-filter-bar" aria-expanded="${faFiltersOpen}">Filters${nFilt ? ` &middot; ${nFilt}` : ""}</button>
      <button type="button" class="chip egfx-chip" id="fa-gfx-btn" title="Shareable graphic"><span class="egfx-chip-glyph" aria-hidden="true">${window.EephusIco ? window.EephusIco("gfx", 12) : ""}</span>Generate GFX</button></div>`;
    const filterBar = `<div class="fa-filter-bar${faFiltersOpen ? " is-open" : ""}" id="fa-filter-bar">
      <span class="filter-label">Type</span>
      ${fchip("type", "all", "All", boardState.type === "all")}
      ${fchip("type", "ufa", `UFA &middot; ${nUfa}`, boardState.type === "ufa")}
      ${fchip("type", "options", `Options &middot; ${nOpt}`, boardState.type === "options")}
      <span class="filter-label" style="margin-left:12px;"><label for="fa-pos-sel">Pos</label></span>
      <select id="fa-pos-sel" class="fa-select">${POS_OPTS.map(([v, l]) =>
        `<option value="${v}"${boardState.pos === v ? " selected" : ""}>${l}</option>`).join("")}</select>
      <span class="filter-label" style="margin-left:12px;">Verdict</span>
      ${["all", "value", "market", "overpay"].map(v => fchip("verdict", v, v === "all" ? "All" : v[0].toUpperCase() + v.slice(1), boardState.verdict === v)).join("")}
      <span class="filter-label" style="margin-left:12px;" title="Bat side for hitters, throwing hand for pitchers">Hand</span>
      ${[["all", "All"], ["L", "L"], ["R", "R"], ["S", "Switch"]].map(([v, l]) => fchip("hand", v, l, boardState.hand === v)).join("")}
    </div>`;
    const _vm = faValueMap(members);
    const valMap = _vm ? `<details class="fa-valmap"><summary>Value map &middot; rational value vs predicted price (current filters)</summary><div class="fa-valmap-wrap" data-export-chart data-export-title="FA value map - rational value vs predicted price">${_vm}</div></details>` : "";
    const table = `<div class="fa-board-wrap"><table class="fa-board-table" data-export data-export-title="MLB Free Agency class board">${head}<tbody>${body}</tbody></table>`
      + (body ? "" : pxState("empty", "No free agents match these filters.")) + `</div>`;

    rows.innerHTML = `<div class="fa-board-layout"><div class="fa-board-main fa-board-tmain">`
      + headEyebrow + tools + filterBar + table + valMap
      + `</div>${boardRail(cls)}</div>`;

    // ---- wiring --------------------------------------------------------------
    const resort = (k, dir, focusSel) => {
      boardState.sort = k; boardState.dir = dir;
      syncToURL(); renderBoard(rows, cls);
      if (window.EEPHUS_GL) window.EEPHUS_GL.wire(rows);
      const again = rows.querySelector(focusSel);
      if (again && again.focus) again.focus();
    };
    rows.querySelectorAll("button[data-fsort]").forEach(b => b.onclick = () => {
      const k = b.dataset.fsort;
      resort(k, boardState.sort === k ? -boardState.dir : faNaturalDir(k), `button[data-fsort="${k}"]`);
    });
    const sel = document.getElementById("fa-sort-sel");
    if (sel) sel.onchange = () => resort(sel.value, faNaturalDir(sel.value), "#fa-sort-sel");
    const dirBtn = document.getElementById("fa-sort-dir");
    if (dirBtn) dirBtn.onclick = () => resort(boardState.sort, -boardState.dir, "#fa-sort-dir");
    const posSel = document.getElementById("fa-pos-sel");
    if (posSel) posSel.onchange = () => {
      boardState.pos = posSel.value; syncToURL(); renderBoard(rows, cls);
      if (window.EEPHUS_GL) window.EEPHUS_GL.wire(rows);
      const again = document.getElementById("fa-pos-sel");
      if (again && again.focus) again.focus();
    };
    // Phone filter drawer (CSS hides the bar under 600px unless it is open).
    // The open state is module-level so a sort or a filter keeps it open.
    const ftog = document.getElementById("fa-filter-toggle");
    if (ftog) ftog.onclick = () => {
      faFiltersOpen = !faFiltersOpen;
      ftog.setAttribute("aria-expanded", String(faFiltersOpen));
      const bar = document.getElementById("fa-filter-bar");
      if (bar) bar.classList.toggle("is-open", faFiltersOpen);
    };
    rows.querySelectorAll("[data-ffilter]").forEach(b => b.onclick = () => {
      boardState[b.dataset.ffilter] = b.dataset.fval;
      syncToURL(); renderBoard(rows, cls);
      if (window.EEPHUS_GL) window.EEPHUS_GL.wire(rows);
    });
    // Detail line: toggled in place (no re-render, so focus stays put) and kept
    // open across sorts and filters through FA_OPEN.
    const toggle = tr => {
      const key = tr.dataset.key;
      const m = cls.members.find(x => x.key === key);
      const btn = tr.querySelector(".fa-xp-btn");
      const next = tr.nextElementSibling;
      if (FA_OPEN.has(key)) {
        FA_OPEN.delete(key);
        if (next && next.classList.contains("fa-detail")) next.remove();
        if (btn) { btn.setAttribute("aria-expanded", "false"); btn.removeAttribute("aria-controls"); }
      } else if (m) {
        FA_OPEN.add(key);
        tr.insertAdjacentHTML("afterend", faDetailRow(m, cls));
        if (btn) { btn.setAttribute("aria-expanded", "true"); btn.setAttribute("aria-controls", "fad-" + key); }
        if (window.EEPHUS_GL && tr.nextElementSibling) window.EEPHUS_GL.wire(tr.nextElementSibling);
      }
    };
    rows.querySelectorAll("tr[data-key]").forEach(tr => {
      const btn = tr.querySelector(".fa-xp-btn");
      if (btn) btn.onclick = e => { e.stopPropagation(); toggle(tr); };
      // A click on a plain part of the row opens the line too; a drag-select
      // does not, so numbers stay copyable, and [data-band] keeps its panel.
      tr.onclick = e => {
        if (e.target.closest("a,button,select,input,[data-band]")) return;
        if (window.getSelection && String(window.getSelection())) return;
        toggle(tr);
      };
    });
    wireBandDismiss();
    rows.querySelectorAll("[data-band]").forEach(el => {
      el.onclick = e => { e.stopPropagation(); openBand(el); };
      el.onkeydown = e => {
        if (e.key === "Enter" || e.key === " " || e.key === "Spacebar") {
          e.preventDefault(); e.stopPropagation(); openBand(el);
        }
      };
    });
    rows.querySelectorAll("[data-fa-goto]").forEach(el => {
      const go = () => { location.hash = faHash() + el.dataset.faGoto; };
      el.onclick = go;
      el.onkeydown = e => {
        if (e.key === "Enter" || e.key === " " || e.key === "Spacebar") { e.preventDefault(); go(); }
      };
    });
    const gfx = document.getElementById("fa-gfx-btn");
    if (gfx) gfx.onclick = () => {
      if (window.EEPHUS_GFX) window.EEPHUS_GFX.open(_faBoardSpec(cls, members));
    };
    fillRowPhotos(rows);
  }

  // Value map: a log-log scatter of rational value (y) vs predicted price (x).
  // The dashed diagonal is fair value (rational == price); a point above it has
  // rational value over its price. Colour is the verdict chip (Deal+ banded by
  // terciles), which is a different cut from the line. Honors the current
  // board filters. Click -> player.
  function faValueMap(members) {
    const pts = members.filter(m => (m.projGuar || 0) > 0 && (m.rational || 0) > 0);
    if (pts.length < 4) return "";
    const W = 760, H = 430, PAD = 54;
    const vals = [];
    pts.forEach(m => { vals.push(m.projGuar / 1e6, m.rational / 1e6); });
    const lo = 1, hi = Math.max(10, ...vals);
    const L = Math.log10, span = (L(hi) - L(lo)) || 1;
    const px = v => PAD + (L(Math.max(v, lo)) - L(lo)) / span * (W - 2 * PAD);
    const py = v => (H - PAD) - (L(Math.max(v, lo)) - L(lo)) / span * (H - 2 * PAD);
    const ticks = [];
    for (let e = 0; Math.pow(10, e) <= hi * 1.0001; e++) ticks.push(Math.pow(10, e));
    const grid = ticks.map(t => `
      <line x1="${px(t).toFixed(1)}" y1="${PAD}" x2="${px(t).toFixed(1)}" y2="${H - PAD}" stroke="var(--border-light)" stroke-width="0.5"/>
      <line x1="${PAD}" y1="${py(t).toFixed(1)}" x2="${W - PAD}" y2="${py(t).toFixed(1)}" stroke="var(--border-light)" stroke-width="0.5"/>
      <text x="${px(t).toFixed(1)}" y="${H - PAD + 14}" text-anchor="middle" font-size="9" fill="var(--text-tertiary)">$${t}M</text>
      <text x="${PAD - 6}" y="${(py(t) + 3).toFixed(1)}" text-anchor="end" font-size="9" fill="var(--text-tertiary)">$${t}M</text>`).join("");
    const diag = `<line x1="${px(lo).toFixed(1)}" y1="${py(lo).toFixed(1)}" x2="${px(hi).toFixed(1)}" y2="${py(hi).toFixed(1)}" stroke="var(--text-tertiary)" stroke-dasharray="5,4" stroke-width="1"/>`;
    const vcol = { value: "var(--accent-green)", market: "var(--text-secondary)", overpay: "var(--accent-red)" };
    // QMLC10: the line is rational value = price, and a dot's colour is its
    // verdict, which is cut on Deal+ terciles, so a MARKET dot can sit just
    // under the line. The legend names both rules; the band basis is read
    // off the artifact like the chip tooltip.
    const edges = ((D.fa_meta || {}).gate2 || {}).verdict_edges || {};
    const bandWhere = edges.band_mode === "group" ? "within position group" : "corpus-wide";
    const dots = pts.map(m => {
      const x = px(m.projGuar / 1e6), y = py(m.rational / 1e6);
      const c = vcol[m.verdict] || "var(--text-tertiary)";
      return `<a href="#${faHash()}player=${encodeURIComponent(m.key || "")}"><circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="4" fill="${c}" fill-opacity="0.72" stroke="${c}" stroke-width="0.5"><title>${esc(m.name)} - price ${money(m.projGuar)} · value ${money(m.rational)} · ${m.verdict || "?"}</title></circle></a>`;
    }).join("");
    return `<svg viewBox="0 0 ${W} ${H}" class="fa-valmap-svg" role="img" aria-label="Rational value versus predicted price scatter">
      <text x="${PAD}" y="18" font-size="11" font-weight="700" fill="var(--text-secondary)">${pts.length} priced free agents · above the line: rational value over price</text>
      <text x="${PAD}" y="33" font-size="10" fill="var(--text-tertiary)">colour: verdict (Deal+ band ${bandWhere})</text>
      <text x="${W / 2}" y="${H - 4}" text-anchor="middle" font-size="10" fill="var(--text-tertiary)">predicted price (projGuarantee)</text>
      <text x="14" y="${H / 2}" text-anchor="middle" font-size="10" fill="var(--text-tertiary)" transform="rotate(-90 14 ${H / 2})">rational value</text>
      ${grid}${diag}
      <text x="${(px(hi) - 4).toFixed(1)}" y="${(py(hi) + 14).toFixed(1)}" text-anchor="end" font-size="9" font-style="italic" fill="var(--text-tertiary)">fair value</text>
      ${dots}
    </svg>`;
  }

  // ---- mini trend line -------------------------------------------------------
  // The compact inline line chart, extracted out of dpwTrendChart (its only
  // caller until 2026-08-03) so the same shape can carry any small series on
  // this page. THIS IS THE SOURCE OF TRUTH: assets/projections.js keeps a
  // shape-identical copy, mirrored the way formatMetric is, because these two
  // surfaces share no module system.
  //
  // The properties worth preserving when copying it: var() colour tokens ONLY,
  // so it is correct in both themes; endpoint VALUE labels, so the reader gets
  // numbers and not just a squiggle; and an invisible fat hit circle over every
  // point, so each one has a hover tooltip without needing a chart library.
  //
  // pts: [{ v: <number>, t: <hover text> }, ...]. Returns "" under two points -
  // a one-point "trend" is a claim the data does not support.
  function miniTrendSVG(pts, opt) {
    const o = opt || {};
    const use = (pts || []).filter(p => p && Number.isFinite(Number(p.v)));
    if (use.length < 2) return "";
    const W = o.w || 220, H = o.h || 74;
    const PT = o.pt != null ? o.pt : 13, PB = o.pb != null ? o.pb : 13;
    const PL = o.pl != null ? o.pl : 5, PR = o.pr != null ? o.pr : 5;
    const vs = use.map(p => Number(p.v));
    let lo = Math.min(...vs), hi = Math.max(...vs);
    const span = (hi - lo) || 1;
    lo -= span * 0.08; hi += span * 0.08;
    const x = i => PL + i * (W - PL - PR) / (use.length - 1);
    const y = v => PT + (hi - v) * (H - PT - PB) / (hi - lo);
    const col = o.color || "var(--accent-gold)";
    const fmt = o.fmt || (v => String(v));
    const line = use.map((p, i) => `${x(i).toFixed(1)},${y(p.v).toFixed(1)}`).join(" ");
    const dots = use.map((p, i) => i === use.length - 1
      ? `<circle cx="${x(i).toFixed(1)}" cy="${y(p.v).toFixed(1)}" r="2.6" fill="${col}"/>`
      : `<circle cx="${x(i).toFixed(1)}" cy="${y(p.v).toFixed(1)}" r="1.5" fill="${col}" fill-opacity="0.75"/>`).join("");
    const hits = use.map((p, i) =>
      `<circle cx="${x(i).toFixed(1)}" cy="${y(p.v).toFixed(1)}" r="7" fill="transparent"><title>${esc(p.t || "")}</title></circle>`).join("");
    const first = use[0], last = use[use.length - 1];
    const firstLbl = `<text x="${PL}" y="${Math.max(8, y(first.v) - 5).toFixed(1)}" font-size="8" fill="var(--text-tertiary)">${esc(fmt(first.v))}</text>`;
    const lastLbl = `<text x="${W - PR}" y="${Math.max(8, y(last.v) - 6).toFixed(1)}" text-anchor="end" font-size="9" font-weight="700" fill="var(--text-secondary)">${esc(fmt(last.v))}</text>`;
    const base = o.baseline === false ? ""
      : `<line x1="${PL}" y1="${H - PB + 3}" x2="${W - PR}" y2="${H - PB + 3}" stroke="var(--border-light)" stroke-width="1"/>`;
    const xlab = (o.xFirst || o.xLast)
      ? `<text x="${PL}" y="${H - 2}" font-size="8" fill="var(--text-tertiary)">${esc(o.xFirst || "")}</text>`
        + `<text x="${W - PR}" y="${H - 2}" text-anchor="end" font-size="8" fill="var(--text-tertiary)">${esc(o.xLast || "")}</text>`
      : "";
    return `<svg viewBox="0 0 ${W} ${H}"${o.style ? ` style="${o.style}"` : ""} role="img"
      aria-label="${esc(o.aria || "trend")}">
      ${base}
      <polyline points="${line}" fill="none" stroke="${col}" stroke-width="1.8" stroke-linejoin="round" stroke-linecap="round"/>
      ${dots}${firstLbl}${lastLbl}${hits}
      ${xlab}
    </svg>`;
  }

  // FA $/WAR by winter as a compact inline line chart: the full signings-implied
  // series in one glance (the old six text rows truncated it and hid the shape -
  // the gradual climb and the 2024 dip read instantly here).
  function dpwTrendChart(series, yrs) {
    const pts = (yrs || []).map(y => ({ y, v: Number(series[y]) })).filter(p => Number.isFinite(p.v));
    if (pts.length < 2) return "";
    const winter = yr => `${Number(yr) - 1}-${String(yr).slice(2)}`;
    const first = pts[0], last = pts[pts.length - 1];
    return miniTrendSVG(pts.map(p => ({ v: p.v, t: `${winter(p.y)} winter: ${money(p.v)}/WAR` })), {
      color: "var(--accent-gold)", fmt: money,
      style: "display:block;width:100%;height:auto;margin:4px 0 0;",
      xFirst: winter(first.y), xLast: winter(last.y),
      aria: `FA dollars per WAR by winter, ${winter(first.y)} through ${winter(last.y)}: ${money(first.v)} to ${money(last.v)}`,
    });
  }

  // ---- rails -----------------------------------------------------------------
  // One rail vocabulary for every FA view. These emit the SAME markup the board
  // rail has always used (.fa-board-rail / .fa-rail-mod / .fa-rail-head /
  // .fa-rail-row / .fa-rail-num), so the three new rails below need no CSS of
  // their own: they inherit the sticky column, the module framing and the
  // monospaced right-aligned number.
  const railMod = (title, body, tip) => body
    ? `<div class="fa-rail-mod"><div class="fa-rail-head" title="${esc(tip || "")}">${title}</div>${body}</div>` : "";
  const railStat = (label, val) =>
    `<div class="fa-rail-row"><span>${label}</span><span class="fa-rail-num">${val}</span></div>`;
  // Wraps a view's main content in the board's two-column layout so a rail can
  // sit beside it. .fa-board-main carries the horizontal scroller, which is what
  // keeps a wide table from dragging the page sideways now that it is no longer
  // a direct child of #fa-rows (see the STICKY RAIL FIX note in site.css).
  const railLayout = (main, rail) => rail
    ? `<div class="fa-board-layout"><div class="fa-board-main">${main}</div>${rail}</div>`
    : main;

  // Signing Tracker rail: the pace of the winter and the model held to account
  // in real time. Same two numbers the eyebrow prints (spent to date, running
  // guarantee MAE) plus the deals those two numbers are made of.
  function trackerRail(cls, signed, scored, spent, mae) {
    const actGuar = m => m.signedGuarNpv ?? m.signedGuar;
    const pace = railStat("signed", `${signed.length} / ${cls.n_members}`)
      + railStat("guaranteed", money(spent))
      + railStat("scored deals", String(scored.length))
      + railStat("guarantee MAE", mae != null ? money(mae) : EM_DASH);
    // Signed magnitude, not absolute: the direction is the interesting half.
    // Deliberately uncoloured - "the market paid above the model" is a miss in
    // both directions, and tinting one of them green would say otherwise.
    const misses = scored.slice()
      .sort((a, b) => Math.abs(actGuar(b) - b.projGuar) - Math.abs(actGuar(a) - a.projGuar))
      .slice(0, 6)
      .map(m => `<div class="fa-rail-row">${clubMark(m.signedTo)}
        <a class="fa-player-link" href="#${faHash()}player=${encodeURIComponent(m.key || "")}">${esc(m.name)}</a>
        <span class="fa-rail-num" title="Actual guarantee minus predicted (NPV basis)">${formatMetric((actGuar(m) - m.projGuar) / 1e6, "surplusM")}</span></div>`).join("");
    return `<aside class="fa-board-rail">
      ${railMod("Winter to date", pace, "Guarantee MAE covers scoreable deals: MLB deals with a frozen ex-ante prediction")}
      ${railMod("Biggest misses so far", misses, "Signed deals by absolute guarantee error")}
    </aside>`;
  }

  // Team Fits rail: who is actually shopping (the clubs whose top fits score
  // highest) and which slots are shut on the club you are looking at.
  function fitsRail(byOrg, meta, team) {
    const mean5 = list => {
      const top = (list || []).slice(0, 5).map(e => e.f && e.f.fit).filter(v => Number.isFinite(v));
      return top.length ? top.reduce((a, b) => a + b, 0) / top.length : null;
    };
    const active = Object.keys(byOrg || {})
      .map(o => ({ o, v: mean5(byOrg[o]), n: (byOrg[o] || []).length }))
      .filter(r => r.v != null)
      .sort((a, b) => b.v - a.v).slice(0, 6)
      .map(r => `<div class="fa-rail-row">${clubMark(r.o)}
        <a href="#${faHash()}view=fits&team=${encodeURIComponent(r.o)}" class="fa-player-link"${r.o === team ? ' aria-current="true"' : ""}>${esc(r.o)}</a>
        <span class="fa-rail-num" title="${r.n} scored fits">${r.v.toFixed(2)}</span></div>`).join("");
    const t = (meta && meta.teams && meta.teams[team]) || {};
    // Every blocked slot, with the incumbent's WAR: this module is the one
    // place the Fits view lists them (the "Not buying" line above the table
    // repeated it and was removed).
    const blocked = (t.blocked || []).map(b =>
      `<div class="fa-rail-row"><span class="fa-block fa-block-${b.t}" title="${b.t === "mlb" ? "MLB incumbent already producing at the slot" : "PROSPX prospect (FV >= 50, near ETA)"}">${esc(b.pos)}<i>${b.t === "mlb" ? "MLB" : "PX"}</i></span>
        <span class="fa-rail-num">${esc(b.n)}${b.w != null ? ` <span class="fa-sub" title="WAR">${formatMetric(b.w, "war")}</span>` : ""}</span></div>`).join("");
    if (!active && !blocked) return "";   // nothing to say, so no sticky column
    return `<aside class="fa-board-rail">
      ${railMod("Most active clubs", active, "Mean fit of each club's top five fits")}
      ${railMod(`Blocked slots &middot; ${esc(team || "")}`, blocked, "Slots held by an MLB incumbent (MLB) or a near-ETA prospect (PX)")}
    </aside>`;
  }

  // Archive rail: the winter graded by what actually happened. Names are plain
  // text, not links - these are historical signings, and #player= resolves
  // against the CURRENT class only.
  function archiveRail(w) {
    const sign = (arr, get, dir) => arr.filter(s => get(s) != null)
      .sort((a, b) => dir * (get(a) - get(b))).slice(0, 6);
    const warRows = sign(w.signings || [], s => s.warTd, -1).map(s =>
      `<div class="fa-rail-row">${clubMark(s.to)}<span>${esc(s.name)}</span>
        <span class="fa-rail-num" title="Realized ${realizedWar()} over the contract's elapsed seasons">${formatMetric(s.warTd, "war")}</span></div>`).join("");
    const surRows = sign(w.signings || [], s => s.surplusTd, -1).map(s =>
      `<div class="fa-rail-row">${clubMark(s.to)}<span>${esc(s.name)}</span>
        <span class="fa-rail-num ${s.surplusTd >= 0 ? "fa-pos" : "fa-neg"}">${formatMetric(s.surplusTd / 1e6, "surplusM")}</span></div>`).join("");
    // The most recent winter has no realized seasons yet (the shipped archive
    // carries zero warTd for it), and an empty aside would still take its 230px
    // sticky column. No realized data, no rail: the table goes back to full
    // width, which is exactly what that winter looked like before.
    if (!warRows && !surRows) return "";
    return `<aside class="fa-board-rail">
      ${railMod("Realized WAR leaders", warRows, `Realized ${realizedWar()} on this winter's contracts to date`)}
      ${railMod("Best realized surplus", surRows, `${realizedWar()} delivered x that season's $/WAR, minus money paid to date`)}
    </aside>`;
  }

  // Market-pulse rail beside the board: best values, biggest projected
  // overpays, class supply by position group, the $/WAR trend.
  function boardRail(cls) {
    const proj = cls.members.filter(m => m.projGuar != null);
    const railRow = m => `<div class="fa-rail-row">${clubMark(m.from)}
      <a class="fa-player-link" href="#${faHash()}player=${encodeURIComponent(m.key || "")}">${esc(m.name)}</a>
      <span class="fa-rail-num">${surplusSpan(m.surplus)}</span></div>`;
    const values = proj.filter(m => m.verdict === "value")
      .sort((a, b) => (b.surplus || 0) - (a.surplus || 0)).slice(0, 6);
    const overpays = proj.filter(m => m.verdict === "overpay")
      .sort((a, b) => (a.surplus || 0) - (b.surplus || 0)).slice(0, 6);
    const groups = {};
    proj.forEach(m => {
      const head = String(m.pos || "").toUpperCase().split("/")[0];
      const g = ["SP", "LHP", "RHP", "P"].includes(head) ? "SP"
        : ["RP", "CL"].includes(head) ? "RP" : head === "C" ? "C"
        : ["1B", "2B", "3B", "SS"].includes(head) ? "IF"
        : ["LF", "CF", "RF", "OF"].includes(head) ? "OF" : "DH";
      groups[g] = (groups[g] || 0) + 1;
    });
    const supply = Object.entries(groups).sort((a, b) => b[1] - a[1])
      .map(([g, n]) => `<div class="fa-rail-row"><span>${g}</span><span class="fa-rail-num">${n}</span></div>`).join("");
    const meta = D.fa_meta || {};
    const series = ((meta.dpw_series || {}).usd_per_war_by_winter) || {};
    const yrs = Object.keys(series).sort();
    // Chart of the FULL series (hover any point for its winter + $/WAR);
    // falls back to the old text rows if there are too few points for a line.
    // The sparkline is a DOOR, not only a picture: it opens the $/WAR by winter
    // detail view. role/tabindex/keydown make it a real button, because a target
    // only a mouse can reach is not one; the hash is read by that view.
    const trendSvg = dpwTrendChart(series, yrs);
    const trend = trendSvg
      ? `<div class="fa-dpw-link" role="button" tabindex="0" data-fa-goto="view=dpw"
          title="Open the $/WAR by winter detail">${trendSvg}<span class="fa-dpw-cue">$/WAR by winter, in full &rarr;</span></div>`
      : yrs.slice(-6).map(y =>
        `<div class="fa-rail-row"><span>${Number(y) - 1}-${String(y).slice(2)}</span><span class="fa-rail-num">${money(series[y])}</span></div>`).join("");
    // M04-08: the eyebrow's figure traced to a winter a reader can see. Since
    // VAL_1 (2026-09-25) the board prices on the series in the sparkline (one
    // written series for /fa/, /projections/ and prospect surplus); the title
    // names a gap only if an artifact still carries one.
    const pricing = cls.dpw_series_pricing || {};
    const anchorY = Object.keys(pricing).filter(y => Number(y) < cls.class_year).sort().pop();
    const oneSeries = Object.keys(pricing).every(y => Number(pricing[y]) === Number(series[y]));
    const basisTitle = oneSeries
      ? "The board, /projections/ and prospect surplus all price on the series in the chart above, carried forward to this winter."
      : "The board's series differs from the series in the chart above; the board prices on its own.";
    const basis = (anchorY && cls.dpw_usd != null)
      ? `<div class="fa-rail-row fa-sub" title="${basisTitle}"><span>Board prices at ${Number(anchorY) - 1}-${String(anchorY).slice(2)} ${money(pricing[anchorY])}, so ${cls.class_year - 1}-${String(cls.class_year).slice(2)} ${money(cls.dpw_usd)}</span></div>`
      : "";
    const mod = railMod;
    return `<aside class="fa-board-rail">
      ${mod("Best projected values", values.map(railRow).join(""), "Largest projected surplus among VALUE verdicts")}
      ${mod("Projected overpays", overpays.map(railRow).join(""), "Most negative projected surplus among OVERPAY verdicts")}
      ${mod("Class supply", supply, "Projected members by position group (a market-model feature)")}
      ${mod("FA $/WAR by winter", trend ? trend + basis : "", "Signings-implied $/WAR (Gate-2 estimator), committed series")}
    </aside>`;
  }

  // ---- Signing Tracker - mode-aware ------------------------------------------
  // Preseason (no observed events): a clear placeholder, because faking a
  // tracker out of projections would conflate the module's two numbers.
  // In-winter: actual-vs-predicted per signing (the model held to account in
  // real time), the option/QO event timeline, and the remaining board.
  function renderTracker(rows, cls) {
    const evs = cls.events || [];
    const signed = cls.members.filter(m => m.status === "signed");
    if (!evs.length && !signed.length) {
      // Not opened yet: the shared unmeasured state (PX-11), never a tracker
      // faked out of projections. The opening is the first observed event, so
      // no date is stamped here (no season-state helper serves one yet).
      rows.innerHTML = `<div class="newsprint-eyebrow"><span class="newsprint-eyebrow-label">Signing Tracker</span></div>`
        + pxState("unmeasured", `<strong>The ${cls.class_year - 1}-${String(cls.class_year).slice(2)} winter has not opened.</strong>
          Signings, option decisions and qualifying offers appear on the day the pipeline first sees them
          (<span data-gl="first_seen_dates">first-seen dates</span>). <a href="#${faHash()}view=board">Class Board</a>:
          ${cls.n_projected} of ${cls.n_members} projected.`, "fa-tracker-closed");
      return;
    }
    const spent = signed.reduce((s, m) => s + (m.signedGuar || 0), 0);
    // Predictions are NPV-basis (deferral-adjusted) - score deltas against
    // the NPV actual where a deferral schedule is on file.
    const actGuar = m => m.signedGuarNpv ?? m.signedGuar;
    const scored = signed.filter(m => m.projGuar != null && m.signedGuar != null && !m.signedMilb);
    const mae = scored.length
      ? scored.reduce((s, m) => s + Math.abs(actGuar(m) - m.projGuar), 0) / scored.length : null;
    const sigRows = signed
      .slice().sort((a, b) => (b.signedDate || "").localeCompare(a.signedDate || "") || (b.signedGuar || 0) - (a.signedGuar || 0))
      .map(m => {
        const actual = m.signedMilb ? "MiLB deal"
          : `${m.signedYears ?? "?"}y / ${money(m.signedGuar)}${m.signedGuarNpv != null ? ` <span class="fa-band">(${money(m.signedGuarNpv)} <span data-gl="deferral_npv">NPV</span>)</span>` : ""}`;
        const pred = m.projGuar != null ? `${m.projYears}y / ${money(m.projGuar)}` : EM_DASH;
        const dGuar = (m.signedGuar != null && m.projGuar != null && !m.signedMilb)
          ? formatMetric((actGuar(m) - m.projGuar) / 1e6, "surplusM") : EM_DASH;
        const realized = (m.rational != null && m.signedGuar > 0 && !m.signedMilb)
          ? Math.round(100 * m.rational / actGuar(m)) : null;
        return `<tr>
          <td>${m.signedDate || EM_DASH}</td>
          <td>${playerLink(m)} <span class="fa-sub">${esc(m.pos || "")}</span>${m.qoAccepted ? ' <span title="Accepted the qualifying offer">QO accepted</span>' : ""}</td>
          <td>${clubTag(m.from)} &rarr; ${clubTag(m.signedTo)}</td>
          <td>${actual}</td>
          <td title="Pre-winter prediction, frozen">${pred}</td>
          <td title="Actual guarantee minus predicted (positive = market paid above model)">${dGuar}</td>
          <td title="Deal+ at the actual price (100 = rational value)">${realized ?? EM_DASH}</td>
        </tr>`;
      }).join("");
    const evRows = evs.filter(e => e.type !== "signing").slice(0, 30).map(e => {
      const label = e.type === "option_declined" ? `declines option${e.optPrice ? " (" + money(e.optPrice) + ")" : ""}; enters class`
        : e.type === "option_exercised" ? `option exercised${e.optPrice ? " (" + money(e.optPrice) + ")" : ""}; off the board`
        : e.type === "qo_offered" ? "receives qualifying offer" : esc(e.type);
      return `<tr><td>${e.date}</td><td><a href="#${faHash()}player=${encodeURIComponent(e.key || "")}" class="fa-player-link"><strong>${esc(e.name || e.key || "")}</strong></a> <span class="fa-sub">${esc(e.pos || "")}</span></td><td>${label}</td></tr>`;
    }).join("");
    const remaining = cls.members.filter(m => m.status !== "signed" && m.status !== "option_exercised" && m.projGuar != null).slice(0, 10);
    const trackerGfx = scored.length
      ? ` &middot; <button class="chip egfx-chip" id="fa-tracker-gfx" title="Shareable graphic"><span class="egfx-chip-glyph" aria-hidden="true">${window.EephusIco ? window.EephusIco("gfx", 12) : ""}</span>Generate GFX</button>`
      : "";
    const trackerMain = `${sigRows ? `<table class="detail-table">
        <thead><tr><th><span data-gl="first_seen_dates">Seen</span></th><th>Player</th><th>From &rarr; To</th><th>Actual</th><th><span data-gl="m_guarantee">Predicted</span></th><th>&Delta; Guar</th><th><span data-gl="deal_plus">Deal+</span> real</th></tr></thead>
        <tbody>${sigRows}</tbody></table>` : ""}
      ${evRows ? `<h3>Option &amp; QO timeline</h3><table class="detail-table">
        <thead><tr><th>Seen</th><th>Player</th><th>Event</th></tr></thead><tbody>${evRows}</tbody></table>` : ""}
      ${remaining.length ? `<h3>Top of the remaining board</h3><table class="detail-table">
        <thead><tr><th>Player</th><th><span data-gl="m_years">projLength</span></th><th><span data-gl="m_guarantee">projGuarantee</span></th><th><span data-gl="m_aav">projAAV</span></th><th>Verdict</th></tr></thead>
        <tbody>${remaining.map(m => `<tr><td>${playerLink(m)} <span class="fa-sub">${esc(m.pos || "")}</span></td>
          <td>${m.projYears}</td><td>${money(m.projGuar)}</td><td>${money(m.projAav)}</td><td>${verdictChip(m)}</td></tr>`).join("")}</tbody></table>` : ""}`;
    rows.innerHTML = `<div class="newsprint-eyebrow"><span class="newsprint-eyebrow-label">Signing Tracker &middot; live</span>
      <span class="newsprint-eyebrow-meta">${signed.length} of ${cls.n_members} signed &middot; ${money(spent)} guaranteed &middot; ${mae != null ? `running guarantee MAE ${money(mae)} over ${scored.length} scored deals` : "no scored MLB deals yet"} &middot; dates are first-seen stamps${trackerGfx}</span></div>
      ${railLayout(trackerMain, trackerRail(cls, signed, scored, spent, mae))}`;
    const tgfx = document.getElementById("fa-tracker-gfx");
    if (tgfx) tgfx.onclick = () => {
      if (window.EEPHUS_GFX) window.EEPHUS_GFX.open(_faTrackerSpec(cls));
    };
  }

  // ---- FA player card (#player=<key>) ----------------------------------------
  function _fvArcSvg(arc) {
    // Tiny inline FV sparkline (20-80 scale). Pure presentation - the points
    // are the exported consensus-FV change history, nothing interpolated.
    const w = 280, h = 56, pad = 4;
    const vals = arc.map(p => p[1]);
    const lo = Math.min(35, ...vals) - 2, hi = Math.max(55, ...vals) + 2;
    const x = i => pad + (w - 2 * pad) * (arc.length === 1 ? 0 : i / (arc.length - 1));
    const y = v => h - pad - (h - 2 * pad) * (v - lo) / (hi - lo);
    const pts = arc.map((p, i) => `${x(i).toFixed(1)},${y(p[1]).toFixed(1)}`).join(" ");
    return `<svg viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" role="img" aria-label="Consensus FV history">
      <polyline points="${pts}" fill="none" stroke="currentColor" stroke-width="1.5"/>
      ${arc.map((p, i) => `<circle cx="${x(i).toFixed(1)}" cy="${y(p[1]).toFixed(1)}" r="2"><title>${p[0]} &middot; FV ${Math.ceil(p[1])}</title></circle>`).join("")}
    </svg>`;
  }

  // Which FA player-card tab the reader last chose. Session-scoped, not URL
  // state: #player=<key> keeps meaning exactly what it meant, and a link shared
  // out of here opens on the card's own first tab rather than on whatever tab
  // the sender happened to be reading.
  let faCardTab = null;

  function bindFaCardTabs(scope, m) {
    // Mount the thread the first time Discussion is opened, mirroring the lazy
    // pattern the prospect and MLB cards use. No-op without the forum layer.
    let forumMounted = false;
    const maybeMountForum = (id) => {
      if (id !== "discussion" || forumMounted) return;
      if (!(window.EephusUI && window.EephusUI.mountForum)) return;
      forumMounted = true;
      try { window.EephusUI.mountForum("fa", m.key, { name: m.name, player_name: m.name, key: m.key }); }
      catch (e) { /* non-fatal */ }
    };
    const active = scope.querySelector("[data-fa-panel]:not([hidden])");
    if (active) maybeMountForum(active.getAttribute("data-fa-panel"));
    const tabs = scope.querySelectorAll("[data-fa-tab]");
    if (!tabs.length) return;
    tabs.forEach(t => t.addEventListener("click", () => {
      const id = t.getAttribute("data-fa-tab");
      faCardTab = id;
      // aria-selected is the ONLY state toggled on the buttons: the stylesheet
      // dims the unselected ones off it, so the visual and the accessible read
      // cannot drift apart.
      scope.querySelectorAll("[data-fa-tab]").forEach(b =>
        b.setAttribute("aria-selected", b.getAttribute("data-fa-tab") === id ? "true" : "false"));
      scope.querySelectorAll("[data-fa-panel]").forEach(pane => {
        if (pane.getAttribute("data-fa-panel") === id) pane.removeAttribute("hidden");
        else pane.setAttribute("hidden", "hidden");
      });
      maybeMountForum(id);
    }));
  }

  // EACH SURFACE SERVES THE ENGINE THAT WON ITS OWN GATE (owner answer M15-1,
  // 2026-09-25). Contracts here stay on the champion path because the market
  // model was gated on it; the clause reads that verdict from fa_meta.gate2, the
  // copy of the committed Gate 2 artifact this page already loads, so it is the
  // measured result and an absent artifact prints nothing.
  function championGateClause(meta) {
    const g2 = (meta || {}).gate2;
    const g = g2 && g2.pooled && g2.pooled.guarantee;
    if (!g || g.mae_model == null || g.mae_base == null) return "";
    const when = g2.generated_at ? `, measured ${esc(String(g2.generated_at).slice(0, 10))}` : "";
    return ` The market model ${g2.pass ? "passed" : "is failing"} <span data-gl="fa_gates">Gate 2</span> on it (guarantee MAE $${Number(g.mae_model).toFixed(2)}M against $${Number(g.mae_base).toFixed(2)}M for its baseline, n ${String(Math.round(Number(g.n))).replace(/\B(?=(\d{3})+(?!\d))/g, ",")}${when}).`;
  }

  function renderPlayer(rows, cls, key) {
    const m = cls.members.find(x => x.key === key);
    if (!m) {
      rows.innerHTML = `<div class="state-message">No class member &ldquo;${esc(key)}&rdquo;. <a href="#${faHash()}view=board">Back to the board</a>.</div>`;
      return;
    }
    const band = (v, p10, p90, fmt) => v == null ? EM_DASH
      : `${fmt(v)}<span class="fa-band"> (${fmt(p10)}-${fmt(p90)})</span>`;
    // Year-by-year projection table: calendar season, age, floor/mean/
    // ceiling eWAR, and that season's escalated $/WAR level. The mean bars
    // ride below as the visual.
    const infl = cls.dpw_infl ?? 0.05;
    // The unified $/WAR path (VAL_5): when the payload carries the written path,
    // each season prints its own level from it; otherwise the legacy escalation.
    const pathBy = cls.dpw_path_by_season || null;
    const yearRows = (m.warPath || []).map((w, i) => {
      const season = cls.class_year + i;
      const lo = (m.warPathP10 || [])[i];
      const hi = (m.warPathP90 || [])[i];
      const dpwT = (pathBy && pathBy[season] != null) ? pathBy[season] : cls.dpw_usd * Math.pow(1 + infl, i);
      const inTerm = m.projYears != null && i < m.projYears;
      return `<tr${inTerm ? "" : ' class="fa-dim"'}>
        <td>${season}${inTerm ? "" : '<span class="fa-sub" title="Beyond the predicted term"> +</span>'}</td>
        <td>${m.age != null ? Math.floor(m.age) + i : EM_DASH}</td>
        <td>${lo != null ? formatMetric(lo, "war") : EM_DASH}</td>
        <td><strong>${formatMetric(w, "war")}</strong></td>
        <td>${hi != null ? formatMetric(hi, "war") : EM_DASH}</td>
        <td title="${pathBy ? "This season's level on the one written $/WAR path" : `The winter's ex-ante $/WAR escalated ${(infl * 100).toFixed(0)}%/yr to this season`}">${money(dpwT)}</td>
      </tr>`;
    }).join("");
    const wp = (m.warPath || []).map((w, i) =>
      `<div class="fa-warbar" title="${cls.class_year + i}: ${formatMetric(w, "war")} WAR${(m.warPathP10 || [])[i] != null ? ` (season P10, floored at 0 WAR, ${formatMetric(m.warPathP10[i], "war")} / P90 ${formatMetric(m.warPathP90[i], "war")})` : ""}"><div style="height:${Math.max(4, Math.min(100, w / 6 * 100)).toFixed(0)}%"></div><span>${String(cls.class_year + i).slice(2)}</span></div>`).join("");
    // The same endpoint-labelled trend the $/WAR rail uses, over the projected
    // WAR path. The bars beside it are a shape; this is the shape WITH numbers
    // on both ends, which is what a decline curve actually needs to be read.
    const wpPath = m.warPath || [];
    const warTrend = miniTrendSVG(
      wpPath.map((w, i) => ({ v: w, t: `${cls.class_year + i}: ${formatMetric(w, "war")} WAR` })),
      { w: 300, h: 66, color: "var(--accent-cyan)", fmt: v => formatMetric(v, "war"),
        style: "display:block;width:100%;max-width:340px;height:auto;margin:2px 0 0;",
        xFirst: String(cls.class_year), xLast: String(cls.class_year + wpPath.length - 1),
        aria: `Projected WAR (fWAR basis) by season, ${cls.class_year} through ${cls.class_year + wpPath.length - 1}` });
    const comps = (m.comps || []).map(c => `<tr><td>${esc(c.name)}</td><td>${c.yr}</td><td>${c.to ? clubTag(c.to) : ""}</td><td>${c.years ?? "?"}y / ${c.guar ? money(c.guar) : "?"}</td></tr>`).join("");
    const fits = (m.fits || []).map(f =>
      `<span class="chip" title="need ${f.need} / window ${f.window} / afford ${f.afford} / park ${f.park} / behavior ${f.behavior}${f.blockedBy ? " - blocked by " + esc(blockedText(f.blockedBy)) : ""}">${clubTag(f.org)}${f.blockedBy ? "*" : ""} &middot; ${f.fit}</span>`).join(" ");
    const signedBlock = m.status === "signed" ? `
      <h3>Signed</h3>
      <p>${clubTag(m.from)} &rarr; <strong>${clubTag(m.signedTo)}</strong> &middot;
      ${m.signedMilb ? "MiLB deal" : `${m.signedYears ?? "?"}y / ${money(m.signedGuar)} (${money(m.signedAav)} AAV)`}
      ${m.signedDate ? `<span class="fa-sub"> &middot; first seen ${m.signedDate}</span>` : ""}
      ${(m.projGuar != null && m.signedGuar != null && !m.signedMilb) ? `<br>vs predicted ${m.projYears}y / ${money(m.projGuar)} &middot; miss ${formatMetric(((m.signedGuarNpv ?? m.signedGuar) - m.projGuar) / 1e6, "surplusM")} &middot; Deal+ at the actual price ${Math.round(100 * m.rational / (m.signedGuarNpv ?? m.signedGuar))}` : ""}</p>` : "";
    const arcBlock = m.fvArc ? `
      <h3>Prospect FV history</h3>
      <div class="fa-arc">${_fvArcSvg(m.fvArc)}</div>
      <p class="fa-note">Consensus FV as a PROSPX prospect, ${m.fvArc[0][0]} to
      ${m.fvArc[m.fvArc.length - 1][0]} &middot;
      <a href="/prospx/#player=${encodeURIComponent(m.key)}">full prospect page &rarr;</a></p>` : "";
    // ---- tabs ---------------------------------------------------------------
    // The FA card was the last untabbed player card of the three modules; this
    // adopts the /projections/ mlbpTabs pattern verbatim (same .mlbp-tabs strip,
    // same .mlbp-tabpanel bodies, same aria-selected-drives-everything rule).
    // NOTHING was dropped: every block that used to run down the page is inside
    // exactly one panel now, and the hero, the two disclosure notes and the back
    // link stay ABOVE the strip because they are card-level, not tab-level.
    //
    // All panels stay in the DOM, hidden ones included, which is what lets the
    // async #fa-current-line fill land whether or not its tab is open.
    const marketPanel = signedBlock + `
      <h3>Predicted market</h3>
      <table class="detail-table"><thead><tr><th><span data-gl="m_years">projLength</span></th><th><span data-gl="m_guarantee">projGuarantee</span></th><th><span data-gl="m_aav">projAAV</span></th><th>Deal <span data-gl="war">WAR</span></th><th><span data-gl="rational_value">Rational</span></th><th><span data-gl="contract_surplus">Surplus</span></th><th><span data-gl="deal_plus">Verdict</span></th></tr></thead>
      <tbody><tr>
        <td>${band(m.projYears, m.projYearsP10, m.projYearsP90, v => v ?? "?")}</td>
        <td>${band(m.projGuar, m.projGuarP10, m.projGuarP90, money)}</td>
        <td>${band(m.projAav, m.projAavP10, m.projAavP90, money)}</td>
        <td>${m.warTotal == null ? "?" : formatMetric(m.warTotal, "war")}</td>
        <td>${m.rational != null ? money(m.rational) : EM_DASH}</td>
        <td>${surplusSpan(m.surplus, m.surplusP10, m.surplusP90)}</td>
        <td>${verdictChip(m)}</td>
      </tr></tbody></table>
      ${(m.surplusP10 != null && m.surplusP90 != null) ? `<p class="fa-note" title="10th and 90th percentile of the contract's value across simulated careers, where a player's seasons move together but not in lockstep, minus the predicted price">Surplus range, P10 &rarr; P90: ${surplusSpan(m.surplusP10)} &rarr; ${surplusSpan(m.surplusP90)}; mean ${surplusSpan(m.surplus)}</p>` : ""}`;
    const seasonPanel = `
      ${yearRows ? `<h3>Season-by-season projection</h3>
      <p class="fa-note">Mean is the <span data-gl="fa_projection_engine">Marcel champion</span> path this page prices on.${championGateClause(D.fa_meta)} /projections/ shows the ML engine's path for the same seasons, the engine its own player-level gate chose (its Accountability view carries the figures), so the two can differ.${m.warSource === "mlb_projections" ? " Seasons 6+: the champion aging curve, continued from this page's season-5 value (the same function /projections/ uses)." : ""}</p>
      <table class="detail-table fa-year-table">
      <thead><tr><th>Season</th><th>Age</th><th><span data-gl="proj_buckets" title="This season's own 10th percentile, floored at 0 WAR. The column is not a path: no career sits at its P10 every season">Season P10</span></th><th>Mean</th><th><span data-gl="proj_buckets" title="This season's own 90th percentile, read the same way">Season P90</span></th><th><span data-gl="winter_dpw">$/WAR</span></th></tr></thead>
      <tbody>${yearRows}</tbody></table>` : ""}
      ${warTrend ? `<div class="fa-war-trend" title="Projected WAR by season (fWAR basis)">${warTrend}</div>` : ""}
      ${wp ? `<div class="fa-warpath" title="Projected WAR by season (fWAR basis); hover a bar for P10/P90">${wp}</div>` : ""}
      <div id="fa-current-line"></div>`;
    const compsPanel = `${arcBlock}
      ${comps ? `<h3>Nearest real comps</h3><table class="detail-table">
        <thead><tr><th>Player</th><th>Winter</th><th>To</th><th>Deal</th></tr></thead><tbody>${comps}</tbody></table>` : ""}
      ${fits ? `<h3>Top team fits</h3><div class="fa-fitchips">${fits}</div>` : ""}`;
    const nonEmpty = h => !!(h && h.replace(/\s+/g, "").length);
    const panels = [
      { id: "market", label: "Market", html: marketPanel },
      { id: "seasons", label: "Season by season", html: seasonPanel },
      { id: "comps", label: "Comps and Fits", html: compsPanel },
    ].filter(p => nonEmpty(p.html));
    // Discussion mount. Gated on the forum layer being present so a build
    // without it never leaves an empty shell; the layer paints its own quiet
    // "No comments yet" state when the Supabase config is blank. FA is the last
    // module card to get one.
    if (window.EephusUI && typeof window.EephusUI.mountForum === "function")
      panels.push({ id: "discussion", label: "Discussion", html: '<div id="eph-forum-mount"></div>' });
    // Restore sanely: keep whichever tab the reader last chose if this card has
    // it, otherwise fall back to the first panel. Deep links stay #player=<key>
    // exactly as before - the tab is a session preference, not URL state, so a
    // shared link always opens on the card's own default.
    const activeId = panels.some(p => p.id === faCardTab) ? faCardTab : (panels[0] || {}).id;
    const strip = panels.length > 1
      ? `<div class="mlbp-tabs" role="tablist">${panels.map(p =>
          `<button type="button" class="chip mlbp-tab" data-fa-tab="${p.id}" role="tab" aria-selected="${p.id === activeId}">${p.label}</button>`).join("")}</div>`
      : "";
    const tabBody = panels.map(p =>
      `<div class="mlbp-tabpanel" data-fa-panel="${p.id}"${p.id === activeId ? "" : " hidden"}>${p.html}</div>`).join("");
    rows.innerHTML = `
      <p><a href="#${faHash()}view=board">&larr; Class Board</a></p>
      <div id="fa-hub"></div>
      <div class="mlbp-hero" id="fa-player-hero">
        <span id="fa-hero-photo"></span>
        <div class="mlbp-hero-main">
          <div class="mlbp-name">${clubA(m.from, teamLogo(m.from), { mark: true })}<h2>${esc(m.name)}</h2></div>
          <div class="fa-sub">${esc(m.pos || "")} &middot; ${m.age != null ? "age " + Math.floor(m.age) : "?"} &middot; ${clubLink(m.from)}${handLabel(m) ? " &middot; " + esc(handLabel(m)) : ""} &middot; ${statusChip(m)}</div>
          <div style="margin-top:8px;"><button class="chip egfx-chip" id="fa-player-gfx" title="Shareable graphic"><span class="egfx-chip-glyph" aria-hidden="true">${window.EephusIco ? window.EephusIco("gfx", 12) : ""}</span>Generate GFX</button></div>
        </div>
        <div class="mlbp-tiles">
          ${m.projGuar != null ? `<div class="mlbp-tile"><span class="mlbp-tile-label">projected</span><span class="mlbp-tile-val">${m.projYears != null ? m.projYears + "y" : "?"} / ${money(m.projGuar)}</span></div>` : ""}
          ${m.projAav != null ? `<div class="mlbp-tile"><span class="mlbp-tile-label">proj AAV</span><span class="mlbp-tile-val">${money(m.projAav)}</span></div>` : ""}
          ${m.dealPlus != null ? `<div class="mlbp-tile"><span class="mlbp-tile-label">Deal+</span><span class="mlbp-tile-val">${Math.round(m.dealPlus)}</span></div>` : ""}
        </div>
      </div>
      ${m.thinPlatform ? `<div class="fa-cba-note">${window.EephusIco ? window.EephusIco("warn", 12) : ""} <span data-gl="thin_platform">Thin platform</span>: ${esc(m.thinPlatform)}. The projection and every price built on it are low-confidence.</div>` : ""}
      ${m.note ? `<div class="fa-cba-note">&#8251; ${esc(m.note)}</div>` : ""}
      ${strip}${tabBody}`;
    bindFaCardTabs(rows, m);
    // Headshot and stat line from the member's own mlbam (QMLP10). A member
    // without one falls back to the links map, which the card fetches anyway
    // for the hub strip; the board never does.
    const fillIdentity = mlbam => {
      if (!mlbam) return;
      // Fill the stat line FIRST: it is the only block here that is content
      // rather than chrome, and a headshot failure must not take it down.
      fillCurrentLine(mlbam);
      const ph = document.getElementById("fa-hero-photo");
      if (ph) {
        // .mlbp-headshot is 96x96.
        ph.outerHTML = `<img class="mlbp-headshot" src="${faHeadshotURL(mlbam, 96)}" alt="" onerror="this.style.visibility='hidden'">`;
      }
    };
    if (m.mlbam) fillIdentity(m.mlbam);
    const gbtn = document.getElementById("fa-player-gfx");
    if (gbtn) gbtn.onclick = () => sharePlayerCard(m, m.mlbam ? { mlbam: m.mlbam } : null);
    // Hub strip (cross-module identity via player_links.json): fetched when a
    // card opens, never blocks the card paint.
    if (window.EEPHUS_HUB) {
      window.EEPHUS_HUB.links().then(L => {
        const row = L && (L.byKey || {})[m.key];
        if (!m.mlbam && row && row.mlbam) fillIdentity(row.mlbam);
        const hub = document.getElementById("fa-hub");
        if (hub && row) hub.innerHTML = window.EEPHUS_HUB.stripHTML(row, "fa");
        const btn = document.getElementById("fa-player-gfx");
        if (btn && row && !m.mlbam) btn.onclick = () => sharePlayerCard(m, row);
      });
    }
  }

  // ---- current-season line --------------------------------------------------
  // The class payload is a MARKET payload: it carries no stats at all, so what a
  // free agent is actually doing right now has to be joined in. The sidecar
  // (data/mlb_current_lines.json, baked by build_site.py) is the shipped MLB
  // leaderboards keyed by MLBAM, lifted verbatim.
  //
  // WHAT IS NOT HERE, deliberately: this site computes no wRC+ and no xFIP, so
  // neither is shown. HEM+ is the offense-rate index the site actually has (100
  // = league average hitter), SEM+/REM+ and Skill FIP are the run-prevention
  // numbers, and season eWAR lives on the MLB player card rather than the
  // leaderboards. Inventing either number to fill the row would be worse than
  // its absence.
  //
  // `line.fip` is NOT the standard FIP. It is the boards' served `fip` field,
  // which is sem_plus / rem_plus fip_skill: every component rate shrunk toward
  // the pitcher's ROLE pool by sample size, plus a role-pool constant. The key
  // keeps its name for compatibility, so the tile label and tooltip are what
  // tell the reader which number this is. The same shrink runs at every sample
  // size, which is why the PITCHER below-threshold note no longer claims the
  // rate stats are shrunk toward league average: K%, BB% and ERA on this tile
  // are the raw line, and only Skill FIP and SEM+/REM+ are shrunk, toward the
  // role pool, qualified or not. The hitter wording was not re-audited here and
  // is left as it was.
  function currentLineHTML(line, meta) {
    if (!line) return "";
    const cell = (label, val, title) => val == null || val === "" ? ""
      : `<div class="mlbp-tile"${title ? ` title="${esc(title)}"` : ""}><span class="mlbp-tile-label">${esc(label)}</span><span class="mlbp-tile-val">${val}</span></div>`;
    const f3 = v => v == null ? null : Number(v).toFixed(3).replace(/^0\./, ".");
    const pct = v => v == null ? null : (Number(v) * 100).toFixed(1) + "%";
    let tiles = "";
    if (line.side === "hit") {
      tiles = cell("PA", line.pa) + cell("AVG/OBP/SLG",
          [f3(line.avg), f3(line.obp), f3(line.slg)].every(x => x != null)
            ? `${f3(line.avg)}/${f3(line.obp)}/${f3(line.slg)}` : null)
        + cell("HR", line.hr) + cell("wOBA", f3(line.woba))
        + cell("HEM+", line.hem, "HEM+: offensive-rate skill index, 100 = league-average hitter")
        + cell("Tier", line.tier ? esc(line.tier) : null);
    } else {
      tiles = cell("IP", line.ip == null ? null : Number(line.ip).toFixed(1))
        + cell("ERA", line.era == null ? null : Number(line.era).toFixed(2))
        + cell("Skill FIP", line.fip == null ? null : Number(line.fip).toFixed(2),
               `Skill FIP: the number ${line.side === "sp" ? "SEM+" : "REM+"} is built on. K, BB, HBP and HR rates shrunk toward the ${line.side === "sp" ? "starter" : "reliever"} pool by sample size; not the standard FIP.`)
        + cell("K%", pct(line.kPct)) + cell("BB%", pct(line.bbPct))
        + cell(line.side === "sp" ? "SEM+" : "REM+", line.side === "sp" ? line.sem : line.rem,
               line.side === "sp" ? "SEM+: starter run-prevention skill index, 100 = the average starter"
                                  : "REM+: reliever skill index, 100 = the average reliever");
    }
    if (!tiles) return "";
    const qual = line.qual === false
      ? (line.side === "hit"
        ? ' <span class="fa-sub">(below the qualifying threshold: rate stats shrunk toward league average)</span>'
        : ' <span class="fa-sub">(below the qualifying threshold: ERA, K% and BB% are the raw line; Skill FIP and '
          + (line.side === "sp" ? "SEM+ are shrunk toward the starter" : "REM+ are shrunk toward the reliever")
          + ' average)</span>')
      : "";
    return `<h3>${esc(meta.season || "")} season to date</h3>
      <div class="mlbp-tiles fa-current-tiles">${tiles}</div>
      <p class="fa-note">From the MLB leaderboards${meta.asOf ? `, as of ${esc(meta.asOf)}` : ""}.${qual}</p>`;
  }

  function fillCurrentLine(mlbam) {
    const host = document.getElementById("fa-current-line");
    if (!host) return;
    load("mlb_current_lines").then(payload => {
      const line = payload && payload.players ? payload.players[String(mlbam)] : null;
      const el = document.getElementById("fa-current-line");
      if (!el) return;
      el.innerHTML = line
        ? currentLineHTML(line, payload)
        : `<h3>${esc((payload && payload.season) || "")} season to date</h3><p class="fa-note">Not on this season's MLB leaderboards (injured, unrostered, or below the minimum playing time).</p>`;
    }).catch(() => { /* sidecar absent - the card simply omits the block */ });
  }

  // Unified per-player share card - declarative since GFX slice 4: this
  // builder now only maps the FA row's DATA (display-formatted with the FA
  // module's own money rules) onto the shared "player-market" template;
  // EEPHUS_HUB.templates owns the tile/section layout. Data priorities are
  // unchanged: the predicted market as TILES (the section no longer repeats
  // projGuarantee/projAAV/verdict - DEDUPE 2026-07-23), rational vs surplus +
  // team fits + comps as the body.
  function sharePlayerCard(m, linkRow) {
    window.EEPHUS_HUB.openCard({
      template: "player-market",
      data: {
        projYears: m.projYears,
        projGuar: m.projGuar != null ? money(m.projGuar) : null,
        projAav: m.projAav != null ? money(m.projAav) : null,
        dealPlus: m.dealPlus != null ? String(Math.round(m.dealPlus)) : null,
        dealWar: m.warTotal != null ? m.warTotal.toFixed(1) : null,
        rational: m.rational != null ? money(m.rational) : null,
        surplus: m.surplus != null ? money(m.surplus) : null,
        priorAav: m.prevAav != null ? money(m.prevAav) : null,
        fits: (m.fits || []).map(f => ({ org: f.org, blocked: !!f.blockedBy, fit: f.fit })),
        comps: (m.comps || []).map(c => ({ name: c.name, yr: c.yr, years: c.years,
          guar: c.guar != null ? money(c.guar) : null, to: c.to })),
      },
      module: "MLB Free Agency",
      accentToken: "--accent-green",
      name: m.name,
      meta: `${m.pos || ""} · ${m.age != null ? "age " + Math.floor(m.age) : "?"} · ${m.from || ""}`,
      sub: m.verdict ? `verdict: ${String(m.verdict).toUpperCase()}` : "",
      // eephus-hub.js draws this hero at a 132x132 SQUARE (g.drawImage(img, x,
      // y, S, S), S = 132) with no object-fit available, so the URL has to
      // arrive square or the face is squashed. faHeadshotURL asks the CDN for
      // exactly that box, face-centered.
      headshotURL: faHeadshotURL(linkRow && linkRow.mlbam, 132),
      url: `eephus.io/fa/#player=${m.key}`,
      filename: `eephus-${m.key}-fa-card.png`,
      caption: "predicted market (projGuarantee) vs rational value · ex-ante",
    });
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
    // Component mini-bars: the same 0-1 score, readable at a glance.
    const cbar = (v, label) => `<div class="fa-cbar" title="${label} ${v}"><div style="width:${Math.round((v || 0) * 100)}%"></div><span>${v}</span></div>`;
    const blockedCell = bb => bb && bb.length
      ? bb.map(b => `<span class="fa-block fa-block-${b.t}" title="${b.t === "mlb" ? "MLB incumbent at the slot" : "PROSPX prospect (FV ≥ 50, near ETA)"}">${esc(b.n)}<i>${b.t === "mlb" ? "MLB" : "PX"}</i></span>`).join(" ")
      : EM_DASH;
    const body = list.map(({ m, f }) => `<tr>
        <td><strong>${playerLink(m)}</strong> <span class="fa-sub">${esc(m.pos || "")} &middot; ${m.age != null ? Math.floor(m.age) : "?"}</span></td>
        <td><strong>${f.fit.toFixed(2)}</strong></td>
        <td>${cbar(f.need, "need")}</td><td>${cbar(f.window, "window")}</td><td>${cbar(f.afford, "afford")}</td><td>${cbar(f.park, "park")}</td><td>${cbar(f.behavior, "behavior")}</td>
        <td>${blockedCell(f.blockedBy)}</td>
        <td>${m.projGuar != null ? `${m.projYears}y / ${money(m.projGuar)}` : EM_DASH}</td>
        <td>${verdictChip(m)}</td>
      </tr>`).join("");
    const fitsGfx = (window.EEPHUS_GFX && list.length)
      ? ` &middot; ${window.EEPHUS_GFX.chipHTML("fa-fits-gfx")}` : "";
    const fitsMain = `<table class="detail-table fa-fits-table">
      <thead><tr><th>Player</th><th><span data-gl="fit_components">Fit</span></th><th title="WAR gap over the incumbent at the position">Need</th><th title="Marginal playoff leverage at the club's baseline wins">Window</th><th title="CBT space vs the predicted AAV (habitual taxpayers keep a floor)">Afford</th><th title="Park factor fit (smallest weight)">Park</th><th title="Biggest deal ever vs this price, last-3-winter outlay, $100M-deal count">Behavior</th><th title="PX = near-ETA PROSPX prospect, MLB = contracted incumbent">Blocked by</th><th>Predicted</th><th>Verdict</th></tr></thead>
      <tbody>${body || `<tr><td colspan="10">No scored fits for ${state.team} in this class.</td></tr>`}</tbody></table>`;
    rows.innerHTML = `<div class="filter-bar"><span class="filter-label">Team</span>${chips}</div>
      <div class="newsprint-eyebrow" style="margin-top:2px;"><span class="newsprint-eyebrow-label">${clubTag(state.team)} fits</span>
      <span class="newsprint-eyebrow-meta">CBT payroll ${money(t.taxPayroll ?? t.committed)} &middot; tax space ${t.space != null ? formatMetric(t.space / 1e6, "surplusM") : EM_DASH}${t.payor ? ` &middot; ${esc(t.payor)}` : ""} &middot; baseline ${t.baseWins ?? "?"}w ${t.baseSrc === "mlb_projections" ? "(projected)" : "(contracted core)"} &middot; biggest deal ever ${money(t.maxGuar)} &middot; last-3-winter outlay ${money(t.recentSpend)}${fitsGfx}</span></div>
      ${railLayout(fitsMain, fitsRail(byOrg, meta, state.team))}`;
    rows.querySelectorAll("[data-fa-team]").forEach(b => b.onclick = () => {
      state.team = b.dataset.faTeam; syncToURL(); render();
    });
    const fgfx = document.getElementById("fa-fits-gfx");
    if (fgfx) fgfx.onclick = () => {
      if (window.EEPHUS_GFX) window.EEPHUS_GFX.open(_faFitsBoardSpec(cls, meta, state.team, list));
    };
  }

  // M04-04: the realized ledger names the WAR it was built on
  // (fa_archive.warBasis); the labels follow the payload instead of assuming
  // one. Every provider token war_source.PROVIDERS knows has its own label,
  // plus "ewar_v3" (eWAR v3, not registered as a provider yet) and "mixed"
  // (a ledger whose rows carry more than one basis). Only a missing or
  // unknown basis prints plain "WAR". POSTEPOCH_10 (PE-Q2): M14 rebuilt the
  // ledger on the displayed eWAR (ewar_v2) on 2026-10-08.
  const REALIZED_WAR_LABELS = {
    bwar: "bWAR", ewar_v2: "eWAR", ewar_v3: "eWAR", ewar_merged: "eWAR",
    fwar: "fWAR", mixed: "mixed-basis WAR",
  };
  function realizedWar() {
    const b = (D.fa_archive || {}).warBasis;
    return REALIZED_WAR_LABELS[b] || "WAR";
  }
  function realizedWarNote() {
    const arc = D.fa_archive || {};
    if (arc.warBasis === "mixed") {
      const counts = Object.entries(arc.warBasisCounts || {})
        .map(([k, n]) => `${esc(REALIZED_WAR_LABELS[k] || k)} ${Number(n).toLocaleString()}`).join(", ");
      return `Realized WAR and surplus mix WAR bases across rows${counts ? " (" + counts + ")" : ""}.`;
    }
    if (arc.warBasis !== "bwar") return "";
    return `Realized WAR and surplus read bWAR: the ledger was last built before the eWAR label and has not been rebuilt${arc.ledgerBuilt ? " (built " + esc(arc.ledgerBuilt) + ")" : ""}.`;
  }

  function renderArchive(rows) {
    const arc = D.fa_archive;
    if (!arc || !arc.winters || !arc.winters.length) {
      rows.innerHTML = `<div class="state-message">Archive not built yet on this deploy; the nightly build writes it.</div>`;
      return;
    }
    const winters = arc.winters.slice().sort((a, b) => b.year - a.year);
    if (!state.winter || !winters.some(w => w.year === state.winter)) state.winter = winters[0].year;
    const chips = winters.map(w =>
      `<button class="chip${w.year === state.winter ? " active" : ""}" data-fa-winter="${w.year}">${w.year - 1}-${String(w.year).slice(2)}</button>`).join("");
    const w = winters.find(x => x.year === state.winter);
    const body = w.signings.map(s => `<tr${s.milb ? ' class="fa-dim"' : ""}>
        <td><strong>${esc(s.name)}</strong> <span class="fa-sub">${esc(s.pos || "")}</span>${s.qo ? ' <span title="Received a qualifying offer">QO</span>' : ""}</td>
        <td>${clubLink(s.from)} &rarr; ${clubTag(s.to)}</td>
        <td>${s.years ?? EM_DASH}</td>
        <td>${s.milb ? "MiLB deal" : money(s.guar)}</td>
        <td>${money(s.aav)}</td>
        <td title="Realized ${realizedWar()} over the contract's elapsed seasons">${s.warTd != null ? formatMetric(s.warTd, "war") : EM_DASH}</td>
        <td title="${realizedWar()} delivered x that season's $/WAR, minus money paid to date">${s.surplusTd != null ? formatMetric(s.surplusTd / 1e6, "surplusM") : EM_DASH}</td>
        <td>${s.done ? "complete" : (s.warTd != null ? "running" : EM_DASH)}</td>
      </tr>`).join("");
    const basisNote = realizedWarNote();
    const arcGfx = (window.EEPHUS_GFX && w.signings.length)
      ? ` &middot; ${window.EEPHUS_GFX.chipHTML("fa-archive-gfx")}` : "";
    const archiveMain = `<table class="detail-table">
      <thead><tr><th>Player</th><th title="From = club holding his rights at signing (a deadline rental shows the acquiring club)">From &rarr; To</th><th>Yrs</th><th>Guarantee</th><th>AAV</th><th>WAR to date</th><th>Surplus to date</th><th>Status</th></tr></thead>
      <tbody>${body}</tbody></table>${basisNote ? `<p class="fa-note">${basisNote}</p>` : ""}`;
    rows.innerHTML = `<div class="filter-bar"><span class="filter-label">Winter</span>${chips}</div>
      <div class="newsprint-eyebrow" style="margin-top:2px;"><span class="newsprint-eyebrow-label">${state.winter - 1}-${String(state.winter).slice(2)} winter</span>
      <span class="newsprint-eyebrow-meta">${w.n} signings &middot; ${money(w.spend_usd)} guaranteed &middot; implied $/WAR ${money(w.dpw_usd)}${w.qo_offered != null ? ` &middot; ${w.qo_offered} qualifying offers` : ""}${arcGfx}</span></div>
      ${railLayout(archiveMain, archiveRail(w))}`;
    rows.querySelectorAll("[data-fa-winter]").forEach(b => b.onclick = () => {
      state.winter = Number(b.dataset.faWinter); syncToURL(); render();
    });
    const agfx = document.getElementById("fa-archive-gfx");
    if (agfx) agfx.onclick = () => {
      if (window.EEPHUS_GFX) window.EEPHUS_GFX.open(_faArchiveBoardSpec(w));
    };
  }

  function renderModel(rows, meta) {
    if (!meta || (!meta.gate1 && !meta.gate2)) {
      rows.innerHTML = `<div class="state-message">Model evaluation not built yet on this deploy; the nightly build writes it.</div>`;
      return;
    }
    const g1 = meta.gate1, g2 = meta.gate2;
    // M04-03: every gate table says when it was measured and on which WAR
    // basis, and says so plainly when that is not the basis the board prices
    // on today. The Gate 2 artifact of 2026-08-19 names no basis at all.
    // The lag sentence prints once: a second lagging gate says so in four
    // words instead of repeating it.
    let lagSaid = false;
    const gateBasis = g => {
      const when = g.generated_at ? String(g.generated_at).slice(0, 10) : null;
      const now = meta.war_provider || null;
      const on = g.war_provider ? `on the ${esc(g.war_provider)} WAR label` : "on a WAR label the artifact does not name";
      const lags = !!now && g.war_provider !== now;
      const lag = !lags ? ""
        : lagSaid ? ` Also not ${esc(now)}: re-run owed.`
        : ` The board prices on ${esc(now)}, so this table does not describe its prices: a re-run on the current label is owed.`;
      if (lags) lagSaid = true;
      return `<div class="fa-note">Measured${when ? " " + esc(when) : ""} ${on}.${lag}</div>`;
    };
    // M04-23: the artifacts' metric keys, read as words (war30 is WAR over
    // player-seasons at age 30 and up, fa_backtest.py). An unknown key prints
    // as itself.
    const METRIC_LBL = { war: "WAR", wrc_plus: "wRC+", fip: "FIP", war30: "WAR, age 30+",
      guarantee: "Guarantee", aav: "AAV", years: "Length (years)",
      mega_guarantee: "Guarantee, deals of $100M+" };
    const pooledRows = (pooled, fmt) => Object.entries(pooled).map(([k, v]) =>
      `<tr><td title="${esc(k)}">${esc(METRIC_LBL[k] || k)}</td><td>${fmt(v.mae_model)}</td><td>${fmt(v.mae_base)}</td><td>${v.n}</td><td>${v.mae_model < v.mae_base ? "&#10003; beats baseline" : "&#10007; behind baseline"}</td></tr>`).join("");
    // Three miss categories, each its own ranked list / Err column. One table,
    // swapped by the small in-section tabs below; default is guarantee.
    const MISS_TABS = [
      ["guar", "Guarantee", "biggest_misses",
        m => `${m.actual_years}y / $${m.actual_guar_mm}M`,
        m => `${m.pred_years}y / $${m.pred_guar_mm}M`,
        m => `${formatMetric(m.err_mm, "rate")}M`],
      ["years", "Length", "biggest_misses_years",
        m => `${m.actual_years}y`, m => `${m.pred_years}y`,
        m => `${formatMetric(m.err_years, "rate")}y`],
      ["aav", "AAV", "biggest_misses_aav",
        m => `$${m.actual_aav_mm}M`, m => `$${m.pred_aav_mm}M`,
        m => `${formatMetric(m.err_aav_mm, "rate")}M`],
    ];
    const missTab = MISS_TABS.find(t => t[0] === modelMissTab) || MISS_TABS[0];
    const missList = (g2 && g2[missTab[2]]) || [];
    const missRows = missList.map(m =>
      `<tr><td>${m.winter}</td><td>${esc(m.player)}</td><td>${esc(m.to_team || "")}</td>
       <td>${missTab[3](m)}</td><td>${missTab[4](m)}</td>
       <td>${missTab[5](m)}</td></tr>`).join("");
    const missTabBar = MISS_TABS.map(t =>
      `<button class="chip${t[0] === missTab[0] ? " active" : ""}" data-mtab="${t[0]}">${t[1]}</button>`).join("");
    rows.innerHTML = `
      <div class="newsprint-eyebrow"><span class="newsprint-eyebrow-label">Model Accountability</span>
      <span class="newsprint-eyebrow-meta"><span data-gl="fa_gates">Gate 1 and Gate 2</span> from the committed eval artifacts, misses included${meta.cba ? ` &middot; ${meta.cba.unverified_records} CBA records await owner verification` : ""}</span></div>
      ${g1 ? `<h3>Gate 1: projection engine (${g1.pass ? "PASSED" : "FAILING"})</h3>
      <div class="fa-note">train &le; N-1, predict N, held-out seasons ${g1.targets ? g1.targets.join(", ") : ""} &middot; <span data-gl="proj_buckets">P10-P90</span> coverage ${g1.coverage_p10_p90 != null ? g1.coverage_p10_p90.toFixed(3) : "?"} (target 0.75-0.85)</div>
      ${gateBasis(g1)}
      <table class="detail-table"><thead><tr><th>Metric</th><th>Model MAE</th><th>Naive baseline</th><th>n</th><th>Verdict</th></tr></thead>
      <tbody>${pooledRows(g1.pooled, v => v == null ? EM_DASH : v.toFixed(3))}</tbody></table>` : ""}
      ${g2 ? `<h3>Gate 2: market model (${g2.pass ? "PASSED" : "FAILING"})</h3>
      <div class="fa-note">forward-chained winters ${g2.test_winters ? g2.test_winters.join(", ") : ""} vs <span data-gl="nearest_comps">nearest-comps</span> baseline &middot; guarantee/AAV in $M</div>
      ${gateBasis(g2)}
      <table class="detail-table"><thead><tr><th>Metric</th><th>Model MAE</th><th>Comps baseline</th><th>n</th><th>Verdict</th></tr></thead>
      <tbody>${pooledRows(g2.pooled, v => v == null ? EM_DASH : v.toFixed(2))}</tbody></table>
      ${g2.pooled_by_pos_group ? `
      <h3>Bias by group</h3>
      <div class="fa-note">Bias = mean predicted minus mean actual ($M; years for
        length rows). Negative: the model under-prices the group.</div>
      <table class="detail-table"><thead><tr><th>Group</th><th>Model MAE</th>
        <th>Model bias</th><th>Baseline bias</th><th>n</th><th>Lean</th></tr></thead>
      <tbody>${Object.entries(g2.pooled_by_pos_group).map(([k, v]) => {
        const b = v.bias_model;
        // Length rows ("years:*") are in years, not $M; they used to print "$0.31M".
        const yrs = String(k).startsWith("years");
        const lean = b == null ? EM_DASH
          : Math.abs(b) < 0.25 ? "no material lean"
          // Plain magnitude, NOT formatMetric: that helper prepends a sign for
          // "rate", which rendered "under-prices by +1.53M" and put a plus sign
          // directly after the word telling you the error is negative.
          : yrs ? (b < 0 ? "too short" : "too long") + " by " + Math.abs(b).toFixed(2) + "y"
          : (b < 0 ? "under-prices" : "over-prices")
            + " by $" + Math.abs(b).toFixed(2) + "M";
        return `<tr><td>${esc(k)}</td>
          <td>${v.mae_model == null ? EM_DASH : v.mae_model.toFixed(2)}</td>
          <td>${b == null ? EM_DASH : (b > 0 ? "+" : "") + b.toFixed(2)}</td>
          <td>${v.bias_base == null ? EM_DASH
                : (v.bias_base > 0 ? "+" : "") + v.bias_base.toFixed(2)}</td>
          <td>${v.n}</td><td>${lean}</td></tr>`;
      }).join("")}</tbody></table>` : ""}
      ${(meta.war_input_divergence && meta.war_input_divergence.before_after) ? `
      <h3>Pricing input change</h3>
      <div class="fa-note">${esc(meta.war_input_divergence.before_after.change)},
        shipped ${esc(meta.war_input_divergence.before_after.shipped)}; same rows
        before and after.${meta.war_input_divergence.diverges && meta.war_input_divergence.pinned_off
          ? ` FA prices use a WAR projection without ${esc(meta.war_input_divergence.pinned_off)};
        MLB Projections keeps it, so the two can show different WAR for one player.` : ""}</div>
      <table class="detail-table"><thead><tr><th>Metric</th><th>Before</th>
        <th>After</th><th>Change</th></tr></thead>
      <tbody>${(meta.war_input_divergence.before_after.rows || []).map(r => {
        const d = r.after - r.before;
        const good = r.better === "lower" ? d < 0 : d > 0;
        return `<tr><td>${esc(r.metric)} <span class="proj-dim">${esc(r.unit)}</span></td>
          <td>${r.before.toFixed(3)}</td><td>${r.after.toFixed(3)}</td>
          <td>${(d > 0 ? "+" : "") + d.toFixed(3)} ${good ? "better" : "worse"}</td></tr>`;
      }).join("")}</tbody></table>` : ""}
      <h3>Biggest misses</h3>
      <div class="fa-filter-bar" style="margin-bottom:8px;">${missTabBar}</div>
      <table class="detail-table"><thead><tr><th>Winter</th><th>Player</th><th>To</th><th>Actual</th><th>Model</th><th>Err</th></tr></thead>
      <tbody>${missRows}</tbody></table>
      <div class="fa-note" style="margin-top:8px;">${(g2.notes || []).map(esc).join(" &middot; ")}</div>` : ""}`;
    rows.querySelectorAll("[data-mtab]").forEach(b => b.onclick = () => {
      modelMissTab = b.dataset.mtab;
      renderModel(rows, meta);
      if (window.EEPHUS_GL) window.EEPHUS_GL.wire(rows);
    });
  }

  // The module glossary moved into the unified /glossary/ data layer
  // (data/glossary.json) - terms here are wrapped as [data-gl] spans instead.

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
