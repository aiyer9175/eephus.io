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
    switch (type) {
      case "int":      return String(Math.round(z));
      case "war":      return z.toFixed(1);
      case "rate":     return sign + abs.toFixed(2);
      case "surplusM": return sign + "$" + abs.toFixed(1) + "M";
      // MINUS but never PLUS. Dropping the sign entirely was harmless for the
      // guarantees and AAVs this surface passes it (all positive) but rendered
      // a NEGATIVE dollar figure as a positive one, and /projections/ prices
      // surplus through this same type, where negatives are now common
      // (rest-of-season control pricing, 2026-08-03). A liability shown as an
      // asset is the worst possible rounding of that number. The leading "+"
      // that `sign` would add belongs to surplusM, where the direction is the
      // point; on a contract guarantee it is noise.
      case "moneyM":   return (z < 0 ? "-" : "") + "$"
                            + (abs >= 100 ? abs.toFixed(0) : abs.toFixed(1)) + "M";
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
    if (!org || !ESPN_SLUGS[org]) return "";
    return `<img class="fa-logo" src="https://a.espncdn.com/i/teamlogos/mlb/500/${ESPN_SLUGS[org]}.png" alt="${esc(org)}" loading="lazy" onerror="this.remove()">`;
  }

  // Deal verdict chip - the plain-English read of Deal+ (band edges are the
  // 2015-2026 corpus terciles; see the deal_verdict glossary entry).
  const VERDICT_META = {
    value: ["VALUE", "Projected to be UNDERPAID - rational value exceeds the predicted price (Deal+ in the corpus top tercile, ≥223)."],
    market: ["MARKET", "Priced about right - rational value and predicted price sit in the corpus middle tercile (Deal+ 109-223)."],
    overpay: ["OVERPAY", "Projected to be OVERPAID - predicted price exceeds rational value (Deal+ in the corpus bottom tercile, <109)."],
  };
  function verdictChip(m) {
    const v = VERDICT_META[m.verdict];
    if (!v) return EM_DASH;
    return `<span class="fa-verdict fa-verdict-${m.verdict}" data-gl="deal_plus" title="${v[1]} Underlying Deal+ ${m.dealPlus ?? "?"} (100 × rational / predicted price).">${v[0]}</span>`;
  }
  function surplusSpan(usd, p10, p90) {
    if (usd == null) return EM_DASH;
    const cls = usd >= 0 ? "fa-pos" : "fa-neg";
    const val = formatMetric(usd / 1e6, "surplusM");
    if (p10 == null || p90 == null) return `<span class="${cls}">${val}</span>`;
    // Same treatment the AAV and Yrs/Guar cells got: the band was hover-only
    // here, which is invisible on a phone and inconsistent for screen readers.
    const band = `Surplus ${val}. Floor to ceiling from the P10 and P90 WAR `
      + `paths: ${formatMetric(p10 / 1e6, "surplusM")} to ${formatMetric(p90 / 1e6, "surplusM")}.`;
    return `<span class="${cls}" data-band tabindex="0" aria-label="${esc(band)}" title="${esc(band)}">${val}</span>`;
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
  }

  function syncToURL() {
    const p = new URLSearchParams();
    if (state.classYear) p.set("class", String(state.classYear));
    if (state.player) p.set("player", state.player);
    else {
      if (state.view !== "board") p.set("view", state.view);
      if (state.view === "fits" && state.team) p.set("team", state.team);
      if (state.view === "archive" && state.winter) p.set("winter", String(state.winter));
    }
    const h = p.toString();
    history.replaceState(null, "", h ? `#${h}` : window.location.pathname);
  }

  async function render() {
    const rows = document.getElementById("fa-rows");
    const chips = document.getElementById("fa-view-chips");
    const banner = document.getElementById("fa-banner");
    if (!rows) return;
    chips.innerHTML = VIEWS.map(([k, label]) =>
      `<button class="chip${state.view === k ? " active" : ""}" data-fa-view="${k}">${label}</button>`).join("")
      + ` <a class="chip" href="/glossary/#cat=${encodeURIComponent("Free Agency")}" title="Every FA term, defined - in the unified site glossary"><span class="chip-glyph" aria-hidden="true">§</span>Glossary</a>`;
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
      return `<button class="chip${on ? " active" : ""}" data-fa-class="${y || ""}" title="${y ? "Projected future class (no signings yet)" : "The current winter (default)"}">${label}${y ? "" : " ·"}</button>`;
    }).join("");
    const wrap = document.createElement("span");
    wrap.style.cssText = "margin-left:14px;display:inline-flex;gap:4px;align-items:center;";
    wrap.innerHTML = `<span class="filter-label">Winter</span>${wchips}`;
    chips.appendChild(wrap);
    wrap.querySelectorAll("[data-fa-class]").forEach(b => b.onclick = () => {
      state.classYear = Number(b.dataset.faClass) || null;
      state.player = null; syncToURL(); render();
    });
    rows.innerHTML = `<div class="state-message is-loading">Loading free-agency data&hellip;</div>`;
    const clsName = state.classYear ? `fa_class_${state.classYear}` : "fa_class";
    try {
      await Promise.all([load(clsName), load("fa_archive"), load("fa_meta")]);
    } catch (e) {
      if (state.classYear) {
        rows.innerHTML = `<div class="state-message">The ${state.classYear - 1}-${String(state.classYear).slice(2)} class isn't exported yet (run the monthly pipeline). <a href="#" onclick="location.hash='';return false;">Back to the current class</a>.</div>`;
        return;
      }
      rows.innerHTML = `<div class="state-message is-error" role="alert">Data failed to load. Refresh to retry;
        if it persists the nightly build is mid-run.
        <button class="chip" id="fa-retry" type="button">Retry</button></div>`;
      const retry = document.getElementById("fa-retry");
      if (retry) retry.onclick = () => render();   // load() re-fetches: failures are not cached
      return;
    }
    const cls = D[clsName], meta = D.fa_meta;
    if (!cls || !cls.members) {
      rows.innerHTML = `<div class="state-message">Free-agency data not exported yet.</div>`;
      return;
    }
    const futureNote = state.classYear
      ? `<div class="fa-cba-note">&#9432; ${state.classYear - 1}-${String(state.classYear).slice(2)} is a PROJECTED future class: contract-expiry members with option/QO statuses; projections priced at that winter's ex-ante $/WAR. No signings or events exist yet.</div>`
      : "";
    banner.innerHTML = futureNote + (cls.cba_carry_forward
      ? `<div class="fa-cba-note">&#9888; CBA rules past 2026-12-01 are <span data-gl="cba_carry_forward">carried forward</span> - thresholds and QO values for this winter are NOT yet collectively bargained.</div>`
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
  }

  function statusChip(m) {
    if (m.status === "signed") {
      const terms = m.signedMilb ? "MiLB deal"
        : `${m.signedYears ?? "?"}y / ${money(m.signedGuar)}`;
      return `<span title="Signed${m.signedDate ? " - first observed " + m.signedDate : ""}. Terms from the class page; the date is the pipeline's observation stamp.">SIGNED ${esc(m.signedTo || "")} ${terms}</span>`;
    }
    if (m.status === "option_exercised") {
      return `<span title="Option exercised - never reached the market (first-seen heuristic; see Tracker).">option exercised</span>`;
    }
    if (m.status === "locked") return `<span title="Contract expires - locked into the class.">UFA</span>`;
    const pct = m.enterProb != null ? ` &middot; P(enter) ${(m.enterProb * 100).toFixed(0)}%` : "";
    const price = m.optPrice ? ` $${(m.optPrice / 1e6).toFixed(1)}M` : "";
    const src = m.enterProbSrc && m.enterProbSrc.startsWith("band_priced")
      ? "Priced from the market model's own P10-P90 band distribution (the option price against the predicted AAV) - v2."
      : "Documented v1 heuristic (mutual/conditional options keep explicit priors).";
    return `<span title="Option-pending - class membership is probabilistic until the option resolves. ${src}">${esc((m.type || "").replace(/_/g, " "))}${price}${pct}</span>`;
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
  function rowPhoto(m) {
    return `<span class="fa-row-photo" data-photo-key="${esc(m.key || "")}"></span>`;
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

  // Board-row headshots: filled async from the cross-module links map
  // (FA rows carry no mlbam locally). One pass per render; rows whose
  // identity didn't resolve keep the empty placeholder (no layout shift).
  function fillRowPhotos(scope) {
    if (!window.EEPHUS_HUB) return;
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
      ? ` <span class="fa-thin" title="${esc(m.thinPlatform)} - projection confidence is LOW; the market line inherits the weakness.">&#9888;</span>` : "";
  }

  function noteBadge(m) {
    return m.note
      ? ` <span class="fa-thin" title="${esc(m.note)}">&#8251;</span>` : "";
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
    const parts = Object.entries(src).map(([k, d]) =>
      `${k} ${d}${stale(d) ? ` <span class="fa-stale" title="${k} last confirmed ${d} - more than 14 days old. Re-run the FA pipeline.">&#9888; stale</span>` : ""}`);
    return `<div class="fa-note fa-sources" title="When each input was last successfully checked for this class, not when the page was built. A quiet market with no new signings still counts as checked; a source that stopped parsing does not.">${gen ? gen + " &middot; " : ""}sources: ${parts.join(" &middot; ")}</div>`;
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
      caption: "predicted market vs rational value - two numbers, never conflated · ex-ante",
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
      caption: "team fit = who they can afford, need, and will actually sign - and who blocks the slot",
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
      caption: "realized WAR and surplus to date - the winter graded by what actually happened",
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
      ? "Option / opt-out - class membership is probabilistic until the option resolves"
      : "UFA - contract expires; locked into the class";
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
  // first, which is what the printed rank numbers mean. BUGFIX 2026-07-31: this
  // key had NO header, so first paint showed no active-sort indicator and the
  // default ordering was a one-way door - once you clicked any column there was
  // no way back to it. "Yrs / Guar" now carries projGuar, and # (rank) resolves
  // to the same key, so the three agree.
  const boardState = { sort: "projGuar", dir: -1, type: "all", pos: "all", verdict: "all", hand: "all" };

  // Which "biggest misses" category the Model Accountability table is showing.
  let modelMissTab = "guar";   // guar | years | aav

  function renderBoard(rows, cls) {
    const sortKey = boardState.sort;
    let members = cls.members.slice();
    if (boardState.type === "ufa") members = members.filter(m => !isOption(m));
    else if (boardState.type === "options") members = members.filter(isOption);
    if (boardState.pos !== "all") members = members.filter(m => posMatches(m, boardState.pos));
    if (boardState.verdict !== "all") members = members.filter(m => m.verdict === boardState.verdict);
    if (boardState.hand !== "all") members = members.filter(m => handOf(m) === boardState.hand);
    members.sort((a, b) => {
      const v = m => {
        // String keys sort as text; "rank" means the board's own default order,
        // so clicking it is the way back from any other sort. BUGFIX 2026-07-31:
        // rank resolved to SURPLUS while the rank numbers were painted in the
        // projGuar default order, so the # column re-ranked the board into a
        // sequence its own numbers contradicted. Both are projGuar now.
        if (sortKey === "name") return String(m.name || "").toLowerCase();
        if (sortKey === "status" || sortKey === "verdict") return String(m[sortKey] || "");
        if (sortKey === "rank") return m.projGuar ?? -1e15;
        return m[sortKey] ?? (sortKey === "age" ? 99 : -1e15);
      };
      return boardState.dir * (v(a) > v(b) ? 1 : v(a) < v(b) ? -1 : 0);
    });
    // Emits a SPAN, not a th: the board head is a CSS grid now, and a th inside
    // a div is invalid markup that browsers silently reparent, which would drop
    // the header row entirely.
    const sHead = (label, key, title) => {
      const on = sortKey === key;
      // a11y (matches the prospx/trademachine sort-header pattern): keyboard
      // reachable, announced as a button, live sort state on aria-sort.
      const ariaSort = on ? (boardState.dir < 0 ? "descending" : "ascending") : "none";
      return `<span class="fa-sort${on ? " is-sorted" : ""}" data-fsort="${key}" title="${esc(title || "Click to sort")}" tabindex="0" role="button" aria-sort="${ariaSort}">${label}${on ? (boardState.dir < 0 ? " ▾" : " ▴") : ""}</span>`;
    };
    const head = `<div class="newsprint-eyebrow" style="margin-top:4px;">
      <span class="newsprint-eyebrow-label">${cls.class_year - 1}-${String(cls.class_year).slice(2)} Class Board</span>
      <span class="newsprint-eyebrow-meta">${cls.members.length} constructed members &middot; ${cls.n_projected} projected &middot; winter $/WAR (ex-ante) ${money(cls.dpw_usd)}, escalating ${((cls.dpw_infl || 0.05) * 100).toFixed(0)}%/yr &middot; <button class="chip egfx-chip" id="fa-gfx-btn" title="Generate a shareable graphic (theme-aware, multiple formats)"><span class="egfx-chip-glyph" aria-hidden="true">&#9636;</span>Generate GFX</button></span>
    </div>`;
    // Filter bar: Type (UFA vs the option family), position group, and verdict.
    const nUfa = cls.members.filter(m => !isOption(m)).length;
    const nOpt = cls.members.length - nUfa;
    const fchip = (group, val, label, on) =>
      `<button class="chip fa-fchip${on ? " active" : ""}" data-ffilter="${group}" data-fval="${val}">${label}</button>`;
    const filterBar = `<div class="fa-filter-bar">
      <span class="filter-label">Type</span>
      ${fchip("type", "all", "All", boardState.type === "all")}
      ${fchip("type", "ufa", `UFA · ${nUfa}`, boardState.type === "ufa")}
      ${fchip("type", "options", `Options · ${nOpt}`, boardState.type === "options")}
      <span class="filter-label" style="margin-left:12px;">Pos</span>
      ${["all", "C", "1B", "2B", "3B", "SS", "IF", "LF", "CF", "RF", "OF", "DH", "SP", "RP"].map(p => fchip("pos", p, p === "all" ? "All" : p, boardState.pos === p)).join("")}
      <span class="filter-label" style="margin-left:12px;">Verdict</span>
      ${["all", "value", "market", "overpay"].map(v => fchip("verdict", v, v === "all" ? "All" : v[0].toUpperCase() + v.slice(1), boardState.verdict === v)).join("")}
      <span class="filter-label" style="margin-left:12px;" title="Bat side for position players, throwing hand for pitchers - the class row carries one letter and it means the side that matters for that role.">Hand</span>
      ${[["all", "All"], ["L", "L"], ["R", "R"], ["S", "Switch"]].map(([v, l]) => fchip("hand", v, l, boardState.hand === v)).join("")}
      <span class="fa-sub fa-filter-count">${members.length} shown</span>
    </div>`;
    const body = members.map((m, i) => {
      // Comps and team fits are NOT on the board row any more (2026-07-31). They
      // were the widest and least scannable content on it - a semicolon list of
      // four historical contracts, and a run of club logos - and BOTH already
      // render in full on the #player card (comps as a table with the signing
      // club, fits as chips carrying their component scores). Dropping them from
      // the row is what buys the card a fixed height without cramping anything.
      const yearsBand = (m.projYearsP10 != null && m.projYearsP90 != null)
        ? `${m.projYearsP10}&ndash;${m.projYearsP90}` : null;
      // Total-WAR P10-P90 band dropped (F-01): summing per-year quantiles does
      // not give the total's quantile, and the underlying per-year marginals
      // undercover realized totals (no league-attrition zero floor), so the
      // band was miscalibrated. Point estimate stays; see REVIEW_QUEUE.
      const dealWar = m.warTotal != null ? formatMetric(m.warTotal, "war") : null;
      // Row-1 deal cells. The P10-P90 bands moved into the title: rendering a
      // point estimate AND its band inside a ~110px track is exactly what made
      // the old cells unreadable, and a band is hover-depth, not scan-depth.
      // The band is carried on `title`, which is HOVER ONLY: it never appears on
      // a touch device and screen readers treat it inconsistently. Inlining the
      // band was already rejected above for good reason (it is what made these
      // cells unreadable), so the band is instead made REACHABLE: aria-label
      // states it for assistive tech, and tabindex makes the cell keyboard
      // focusable so it is not mouse-only.
      //
      // data-band completes it (2026-08-07): openBand above reads this cell's
      // aria-label into a tap-to-open panel, so the touch half is no longer
      // missing either. Inlining the band into the cell stays rejected.
      // KNOWN BAND DEFECT, disclosed rather than hidden (plan item D6). The
      // bands come from a FLAT ratio applied to the point estimate, not from a
      // per-tier fit, so at the top of the market the upper end goes somewhere
      // no contract has ever been. Making the band reachable above would
      // otherwise surface an absurd number with nothing telling a reader it is
      // known to be wrong. The proper fix is per-tier band scaling behind a lab
      // gate, which is not done; this is the honest interim.
      const aavWild = m.projAav > 0 && m.projAavP90 != null
                      && m.projAavP90 > m.projAav * 2.5;
      const aavBand = `Predicted average annual value ${money(m.projAav)}. `
        + `P10 to P90 ${money(m.projAavP10)} to ${money(m.projAavP90)}.`
        + (aavWild ? " Note: this band comes from a flat ratio rather than a"
                     + " per-tier fit, so the upper end is unrealistically wide"
                     + " at the top of the market." : "");
      const aavCell = m.projAav == null ? EM_DASH
        : `<span data-band tabindex="0" aria-label="${esc(aavBand)}" title="${esc(aavBand)}">${money(m.projAav)}</span>`;
      const guarBand = `Predicted term and total guarantee. Length P10 to P90 ${m.projYearsP10 ?? "?"} to ${m.projYearsP90 ?? "?"} years; guarantee P10 to P90 ${money(m.projGuarP10)} to ${money(m.projGuarP90)}.`;
      const guarCell = m.projGuar == null ? EM_DASH
        : `<span data-band tabindex="0" aria-label="${esc(guarBand)}" title="${esc(guarBand)}">${m.projYears != null ? m.projYears + "y / " : ""}${money(m.projGuar)}</span>`;
      const trCls = [
        (m.projGuar == null || m.status === "option_exercised") ? "fa-dim" : "",
        isOption(m) ? "fa-row-opt" : "",
      ].filter(Boolean).join(" ");
      // PROSPX-pattern card (Lane B, 2026-07-30), same treatment the Projections
      // board took. Row 1 is identity and the verdict-bearing numbers; row 2 is a
      // tape carrying the PREDICTED DEAL, which is the thing a reader actually
      // came for and which the table had squeezed into four cells alongside their
      // own P10-P90 bands.
      const chip = (label, val, title) => (val == null || val === EM_DASH ? "" :
        `<div class="mlb-chip"${title ? ` title="${title}"` : ""}><b>${label}</b>${val}</div>`);
      // Phase H (docs/master-plan-2026-07-29-efv-fa.md): these were computed and
      // carried in the payload but rendered nowhere. warCvar10 is the mean of the
      // worst decile of outcomes, i.e. what the deal looks like when it goes
      // wrong, which is exactly what a surplus point estimate hides.
      const risk = [
        m.warCvar10 != null ? chip("downside WAR", formatMetric(m.warCvar10, "war"),
          "Conditional value at risk: the MEAN of the worst 10 percent of outcome paths, not the 10th percentile itself. What the contract looks like when it goes wrong.") : "",
        m.pAnyStar != null ? chip("star odds", (m.pAnyStar * 100).toFixed(0) + "%",
          "Probability of at least one star-level season over the predicted term.") : "",
        m.optKind ? chip("option", esc(String(m.optKind)) + (m.optHeldBy ? " / " + esc(String(m.optHeldBy)) : ""),
          "Contract option on the deal: which kind, and who holds it." + (m.optValue != null ? ` Modelled value ${money(m.optValue)}.` : "")) : "",
      ].join("");
      // Tape order runs production -> value -> risk -> shape, and every chip in
      // it has a matching button in the sort bar above the board (see FA_SORTBAR).
      const tape = `<div class="mlb-tape"><div class="mlb-tape-inner">
        ${chip("WAR y1", m.warY1 != null ? formatMetric(m.warY1, "war") : null, "Projected year-1 bWAR")}
        ${chip("deal WAR", dealWar, "Projected bWAR over the predicted term (floor-ceiling from the Gate-1 probability buckets)")}
        ${chip("rational", m.rational != null ? money(m.rational) : null, "Convex-priced NPV of the projected production: what the deal is worth if you pay for value rather than for name")}
        ${risk}
        ${chip("yrs P10-P90", yearsBand, "The predicted term's P10-P90 range. The point estimate is in the Yrs / Guar column.")}
      </div></div>`;
      return `<div class="mlb-card fa-card${trCls ? " " + trCls : ""}" tabindex="0" role="button"
          data-card-href="#player=${encodeURIComponent(m.key)}">
        <span class="mlb-rank">${i + 1}</span>
        <div class="fa-id">
          ${rowPhoto(m)}
          <span class="mlb-name">${playerLink(m, { noPhoto: true })}${noteBadge(m)}${thinBadge(m)} ${typeTag(m)}</span>
          <span class="mlb-sub">${esc(m.pos || "")} &middot; ${m.age != null ? m.age.toFixed(1) : "?"} &middot; ${teamLogo(m.from)}${esc(m.from || "")}${handOf(m) ? " &middot; " + handShort(m) : ""}${m.qo ? ` &middot; <span title="Received a qualifying offer: signing him costs the new club draft compensation">QO</span>` : ""}</span>
        </div>
        <span class="mlb-metric"><span class="mlb-metric-label">Status</span><span class="fa-statustext">${statusChip(m)}</span></span>
        <span class="mlb-metric"><span class="mlb-metric-label">proj AAV</span>${aavCell}</span>
        <span class="mlb-metric"><span class="mlb-metric-label">Yrs / Guar</span>${guarCell}</span>
        <span class="mlb-metric"><span class="mlb-metric-label">Surplus</span>${surplusSpan(m.surplus, m.surplusP10, m.surplusP90)}</span>
        <span class="mlb-metric"><span class="mlb-metric-label">Verdict</span>${verdictChip(m)}</span>
        ${tape}
      </div>`;
    }).join("");
    const _vm = faValueMap(members);
    const valMap = _vm ? `<details class="fa-valmap"><summary>Value map &middot; rational value vs predicted price (current filters)</summary><div class="fa-valmap-wrap" data-export-chart data-export-title="FA value map - rational value vs predicted price">${_vm}</div></details>` : "";
    // Card-head tracks must mirror the .fa-card grid exactly, so both read from
    // one definition rather than two that can drift. Every flexible track is
    // minmax(0,...) - a bare fr refuses to shrink below min-content and a long
    // signed-status string would blow the row out sideways.
    const FA_TRACKS = "34px minmax(0,1.85fr) minmax(0,1.2fr) 84px 118px 92px 84px";
    // The row-2 tape chips are NOT track-aligned with the header (they live in
    // the reserved band at the card bottom and scroll inside their own box), so
    // they get their own strip of sort buttons - the /fantasy/ .ff-sortbar
    // pattern. This is what restores every sort the table had, plus the ones it
    // never exposed, WITHOUT re-widening row 1 back into a twelve-column table.
    const FA_SORTBAR = `<div class="mlb-sortbar"><span class="mlb-sortbar-lbl">Sort tape</span>
      ${sHead(`<span data-gl="war">WAR</span> y1`, "warY1", "Projected year-1 bWAR")}
      ${sHead("deal WAR", "warTotal", "Projected bWAR over the predicted term, with floor-ceiling buckets")}
      ${sHead(`<span data-gl="rational_value">rational</span>`, "rational", "Convex-priced NPV of the projected production")}
      ${sHead("downside WAR", "warCvar10", "Mean of the worst 10 percent of outcome paths - what the deal looks like when it goes wrong")}
      ${sHead("star odds", "pAnyStar", "Probability of at least one star-level season over the predicted term")}
      ${sHead("length", "projYears", "Predicted contract length in years")}
      ${sHead("age", "age", "Player age carried on the class row")}
    </div>`;
    // # and Player join the sortable set; the table had them as inert th.
    rows.innerHTML = head + filterBar + valMap + `<div class="fa-board-layout"><div class="fa-board-main">
      ${FA_SORTBAR}
      <div class="mlb-card-head" style="grid-template-columns:${FA_TRACKS};">
        ${sHead("#", "rank", "Board position under the current sort. The default order is the predicted guarantee.")}
        ${sHead("Player", "name", "Sort by name")}
        ${sHead("Status", "status", "Where the player is in the market")}
        ${sHead("proj AAV", "projAav", "Predicted average annual value. Tap or click a cell for its P10-P90 band.")}
        ${sHead("Yrs / Guar", "projGuar", "Predicted term and total guarantee. Tap or click a cell for the P10-P90 bands.")}
        ${sHead(`<span data-gl="contract_surplus">Surplus</span>`, "surplus", "Rational value minus predicted price. Tap or click a cell for the floor/ceiling range.")}
        ${sHead(`<span data-gl="deal_plus">Verdict</span>`, "verdict", "The deal call, from surplus banded within the player's own group")}
      </div>
      <div class="mlb-card-list">${body || '<div class="fa-sub" style="padding:2rem;text-align:center;">No free agents match these filters.</div>'}</div></div>
      ${boardRail(cls)}</div>`;
    rows.querySelectorAll(".fa-card").forEach(c => { c.style.gridTemplateColumns = FA_TRACKS; });
    rows.querySelectorAll(".fa-card[data-card-href]").forEach(c => {
      const open = () => { location.hash = c.dataset.cardHref.replace(/^#/, ""); };
      // [data-band] joins the a/button guard: those cells are their own control
      // now, and a tap on one must show the band rather than leave the board.
      c.onclick = e => { if (!e.target.closest("a,button,[data-band]")) open(); };
      c.onkeydown = e => {
        if ((e.key === "Enter" || e.key === " ") && !e.target.closest("a,button,[data-band]")) { e.preventDefault(); open(); }
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
    rows.querySelectorAll("[data-fsort]").forEach(h => {
      const doSort = () => {
        const k = h.dataset.fsort;
        if (boardState.sort === k) boardState.dir = -boardState.dir;
        else { boardState.sort = k; boardState.dir = -1; }
        renderBoard(rows, cls);
        if (window.EEPHUS_GL) window.EEPHUS_GL.wire(rows);
      };
      h.onclick = doSort;
      // Enter/Space sort from the keyboard; preventDefault stops Space from
      // scrolling the page (same contract as the prospx sort headers).
      h.onkeydown = (e) => {
        if (e.key === "Enter" || e.key === " " || e.key === "Spacebar") { e.preventDefault(); doSort(); }
      };
    });
    // In-module jumps that are not player cards (today: the rail's $/WAR
    // sparkline -> #view=dpw). faHash() keeps the selected winter on the URL,
    // which A5 established: dropping class= reloads the wrong class.
    rows.querySelectorAll("[data-fa-goto]").forEach(el => {
      const go = () => { location.hash = faHash() + el.dataset.faGoto; };
      el.onclick = go;
      el.onkeydown = e => {
        if (e.key === "Enter" || e.key === " " || e.key === "Spacebar") { e.preventDefault(); go(); }
      };
    });
    rows.querySelectorAll("[data-ffilter]").forEach(b => b.onclick = () => {
      boardState[b.dataset.ffilter] = b.dataset.fval;
      renderBoard(rows, cls);
      if (window.EEPHUS_GL) window.EEPHUS_GL.wire(rows);
    });
    const gfx = document.getElementById("fa-gfx-btn");
    if (gfx) gfx.onclick = () => {
      if (window.EEPHUS_GFX) window.EEPHUS_GFX.open(_faBoardSpec(cls, members));
    };
    fillRowPhotos(rows);
  }

  // Value map: a log-log scatter of rational value (y) vs predicted price (x).
  // The dashed diagonal is fair value (rational == price); points ABOVE are
  // value (projected underpaid), BELOW are overpay - colored by verdict so the
  // cloud reads at a glance. Honors the current board filters. Click -> player.
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
    const dots = pts.map(m => {
      const x = px(m.projGuar / 1e6), y = py(m.rational / 1e6);
      const c = vcol[m.verdict] || "var(--text-tertiary)";
      return `<a href="#${faHash()}player=${encodeURIComponent(m.key || "")}"><circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="4" fill="${c}" fill-opacity="0.72" stroke="${c}" stroke-width="0.5"><title>${esc(m.name)} - price ${money(m.projGuar)} · value ${money(m.rational)} · ${m.verdict || "?"}</title></circle></a>`;
    }).join("");
    return `<svg viewBox="0 0 ${W} ${H}" class="fa-valmap-svg" role="img" aria-label="Rational value versus predicted price scatter">
      <text x="${PAD}" y="20" font-size="11" font-weight="700" fill="var(--text-secondary)">${pts.length} priced free agents · above the line = value, below = overpay</text>
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
      .map(m => `<div class="fa-rail-row">${teamLogo(m.signedTo)}
        <a class="fa-player-link" href="#${faHash()}player=${encodeURIComponent(m.key || "")}">${esc(m.name)}</a>
        <span class="fa-rail-num" title="Actual guarantee minus predicted (NPV basis)">${formatMetric((actGuar(m) - m.projGuar) / 1e6, "surplusM")}</span></div>`).join("");
    return `<aside class="fa-board-rail">
      ${railMod("Winter to date", pace, "How much of the class has signed, what it cost, and the model's running guarantee error over the deals that are scoreable (MLB deals with a frozen ex-ante prediction)")}
      ${railMod("Biggest misses so far", misses, "Signed deals ranked by the size of the model's guarantee error, largest first - published, not hidden")}
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
      .map(r => `<div class="fa-rail-row">${teamLogo(r.o)}
        <a href="#${faHash()}view=fits&team=${encodeURIComponent(r.o)}" class="fa-player-link"${r.o === team ? ' aria-current="true"' : ""}>${esc(r.o)}</a>
        <span class="fa-rail-num" title="${r.n} scored fits">${r.v.toFixed(2)}</span></div>`).join("");
    const t = (meta && meta.teams && meta.teams[team]) || {};
    const blocked = (t.blocked || []).slice(0, 8).map(b =>
      `<div class="fa-rail-row"><span class="fa-block fa-block-${b.t}" title="${b.t === "mlb" ? "MLB incumbent already producing at the slot" : "PROSPX prospect (FV >= 50, near ETA)"}">${esc(b.pos)}<i>${b.t === "mlb" ? "MLB" : "PX"}</i></span>
        <span class="fa-rail-num">${esc(b.n)}</span></div>`).join("");
    if (!active && !blocked) return "";   // nothing to say, so no sticky column
    return `<aside class="fa-board-rail">
      ${railMod("Most active clubs", active, "Clubs ranked by the mean fit score of their own top five fits - the orgs the needs/afford/behavior model thinks are actually in this market")}
      ${railMod(`Blocked slots &middot; ${esc(team || "")}`, blocked, "Positions this club is NOT shopping at: the needs matrix found an incumbent (MLB) or a near-ETA prospect (PX) already holding the slot")}
    </aside>`;
  }

  // Archive rail: the winter graded by what actually happened. Names are plain
  // text, not links - these are historical signings, and #player= resolves
  // against the CURRENT class only.
  function archiveRail(w) {
    const sign = (arr, get, dir) => arr.filter(s => get(s) != null)
      .sort((a, b) => dir * (get(a) - get(b))).slice(0, 6);
    const warRows = sign(w.signings || [], s => s.warTd, -1).map(s =>
      `<div class="fa-rail-row">${teamLogo(s.to)}<span>${esc(s.name)}</span>
        <span class="fa-rail-num" title="Realized bWAR over the contract's elapsed seasons">${formatMetric(s.warTd, "war")}</span></div>`).join("");
    const surRows = sign(w.signings || [], s => s.surplusTd, -1).map(s =>
      `<div class="fa-rail-row">${teamLogo(s.to)}<span>${esc(s.name)}</span>
        <span class="fa-rail-num ${s.surplusTd >= 0 ? "fa-pos" : "fa-neg"}">${formatMetric(s.surplusTd / 1e6, "surplusM")}</span></div>`).join("");
    // The most recent winter has no realized seasons yet (the shipped archive
    // carries zero warTd for it), and an empty aside would still take its 230px
    // sticky column. No realized data, no rail: the table goes back to full
    // width, which is exactly what that winter looked like before.
    if (!warRows && !surRows) return "";
    return `<aside class="fa-board-rail">
      ${railMod("Realized WAR leaders", warRows, "Most bWAR actually delivered on this winter's contracts so far - realized, not projected")}
      ${railMod("Best realized surplus", surRows, "Realized surplus to date: WAR delivered x that season's estimated $/WAR, minus the money prorated to date")}
    </aside>`;
  }

  // Market-pulse rail beside the board: best values, biggest projected
  // overpays, class supply by position group, the $/WAR trend.
  function boardRail(cls) {
    const proj = cls.members.filter(m => m.projGuar != null);
    const railRow = m => `<div class="fa-rail-row">${teamLogo(m.from)}
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
          title="Open the $/WAR by winter detail - the full signings-implied series, how it is estimated, and what every future season escalates against">${trendSvg}<span class="fa-dpw-cue">$/WAR by winter, in full &rarr;</span></div>`
      : yrs.slice(-6).map(y =>
        `<div class="fa-rail-row"><span>${Number(y) - 1}-${String(y).slice(2)}</span><span class="fa-rail-num">${money(series[y])}</span></div>`).join("");
    const mod = railMod;
    return `<aside class="fa-board-rail">
      ${mod("Best projected values", values.map(railRow).join(""), "Largest projected Contract Surplus among VALUE verdicts - rational value furthest above the predicted price")}
      ${mod("Projected overpays", overpays.map(railRow).join(""), "Most negative projected Contract Surplus among OVERPAY verdicts")}
      ${mod("Class supply", supply, "Projected members by position group - thin groups inflate prices (a market-model feature)")}
      ${mod("FA $/WAR by winter", trend, "The signings-implied $/WAR series (Gate-2 estimator) - the gradual climb is why every future season escalates")}
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
      rows.innerHTML = `<div class="newsprint-eyebrow"><span class="newsprint-eyebrow-label">Signing Tracker</span>
        <span class="newsprint-eyebrow-meta">preseason - goes live with the first observed event</span></div>
        <div class="state-message">
          <div class="state-message-title">The ${cls.class_year - 1}-${String(cls.class_year).slice(2)} winter hasn't opened</div>
          <div class="state-message-body">Signings, option decisions and qualifying offers land here as the
          daily pipeline first observes them (Spotrac publishes no dates, so every event carries its
          observation stamp). The winter runs in sequence: contract options resolve in the days after
          the World Series, qualifying offers are extended and decided, and then the market opens.
          Until then the Class Board carries the projected market -
          ${cls.n_projected} of ${cls.n_members} members projected.</div>
        </div>`;
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
          : `${m.signedYears ?? "?"}y / ${money(m.signedGuar)}${m.signedGuarNpv != null ? `<span class="fa-band" title="Deferral-adjusted NPV at the platform 9% rate - the basis the prediction speaks"> (${money(m.signedGuarNpv)} NPV)</span>` : ""}`;
        const pred = m.projGuar != null ? `${m.projYears}y / ${money(m.projGuar)}` : EM_DASH;
        const dGuar = (m.signedGuar != null && m.projGuar != null && !m.signedMilb)
          ? formatMetric((actGuar(m) - m.projGuar) / 1e6, "surplusM") : EM_DASH;
        const realized = (m.rational != null && m.signedGuar > 0 && !m.signedMilb)
          ? Math.round(100 * m.rational / actGuar(m)) : null;
        return `<tr>
          <td>${m.signedDate || EM_DASH}</td>
          <td>${playerLink(m)} <span class="fa-sub">${esc(m.pos || "")}</span>${m.qoAccepted ? ' <span title="Accepted the qualifying offer">QO accepted</span>' : ""}</td>
          <td>${teamLogo(m.from)}${esc(m.from || "")} &rarr; ${teamLogo(m.signedTo)}${esc(m.signedTo || "")}</td>
          <td>${actual}</td>
          <td title="The model's pre-winter prediction - frozen, not re-fit">${pred}</td>
          <td title="Actual guarantee minus predicted (positive = market paid above model)">${dGuar}</td>
          <td title="Deal+ at the ACTUAL price - 100 = rational value">${realized ?? EM_DASH}</td>
        </tr>`;
      }).join("");
    const evRows = evs.filter(e => e.type !== "signing").slice(0, 30).map(e => {
      const label = e.type === "option_declined" ? `declines option${e.optPrice ? " (" + money(e.optPrice) + ")" : ""} - enters class`
        : e.type === "option_exercised" ? `option exercised${e.optPrice ? " (" + money(e.optPrice) + ")" : ""} - off the board`
        : e.type === "qo_offered" ? "receives qualifying offer" : esc(e.type);
      return `<tr><td>${e.date}</td><td><a href="#${faHash()}player=${encodeURIComponent(e.key || "")}" class="fa-player-link"><strong>${esc(e.name || e.key || "")}</strong></a> <span class="fa-sub">${esc(e.pos || "")}</span></td><td>${label}</td></tr>`;
    }).join("");
    const remaining = cls.members.filter(m => m.status !== "signed" && m.status !== "option_exercised" && m.projGuar != null).slice(0, 10);
    const trackerGfx = scored.length
      ? ` &middot; <button class="chip egfx-chip" id="fa-tracker-gfx" title="Generate a shareable graphic of the signing tracker"><span class="egfx-chip-glyph" aria-hidden="true">&#9636;</span>Generate GFX</button>`
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
    rows.innerHTML = `<div class="newsprint-eyebrow"><span class="newsprint-eyebrow-label">Signing Tracker - live</span>
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

  function renderPlayer(rows, cls, key) {
    const m = cls.members.find(x => x.key === key);
    if (!m) {
      rows.innerHTML = `<div class="state-message">No class member &ldquo;${esc(key)}&rdquo;. <a href="#${faHash()}view=board">Back to the board</a>.</div>`;
      return;
    }
    const band = (v, p10, p90, fmt) => v == null ? EM_DASH
      : `${fmt(v)}<span class="fa-band"> (${fmt(p10)}&ndash;${fmt(p90)})</span>`;
    // Year-by-year projection table: calendar season, age, floor/mean/
    // ceiling bWAR, and that season's escalated $/WAR level. The mean bars
    // ride below as the visual.
    const infl = cls.dpw_infl ?? 0.05;
    const yearRows = (m.warPath || []).map((w, i) => {
      const season = cls.class_year + i;
      const lo = (m.warPathP10 || [])[i];
      const hi = (m.warPathP90 || [])[i];
      const dpwT = cls.dpw_usd * Math.pow(1 + infl, i);
      const inTerm = m.projYears != null && i < m.projYears;
      return `<tr${inTerm ? "" : ' class="fa-dim"'}>
        <td>${season}${inTerm ? "" : '<span class="fa-sub" title="Beyond the predicted term - shown because any longer offer prices these seasons"> +</span>'}</td>
        <td>${m.age != null ? Math.floor(m.age) + i : EM_DASH}</td>
        <td>${lo != null ? formatMetric(lo, "war") : EM_DASH}</td>
        <td><strong>${formatMetric(w, "war")}</strong></td>
        <td>${hi != null ? formatMetric(hi, "war") : EM_DASH}</td>
        <td title="The winter's ex-ante $/WAR escalated ${(infl * 100).toFixed(0)}%/yr to this season">${money(dpwT)}</td>
      </tr>`;
    }).join("");
    const wp = (m.warPath || []).map((w, i) =>
      `<div class="fa-warbar" title="${cls.class_year + i}: ${formatMetric(w, "war")} bWAR${(m.warPathP10 || [])[i] != null ? ` (floor ${formatMetric(m.warPathP10[i], "war")} / ceiling ${formatMetric(m.warPathP90[i], "war")})` : ""}"><div style="height:${Math.max(4, Math.min(100, w / 6 * 100)).toFixed(0)}%"></div><span>${String(cls.class_year + i).slice(2)}</span></div>`).join("");
    // The same endpoint-labelled trend the $/WAR rail uses, over the projected
    // WAR path. The bars beside it are a shape; this is the shape WITH numbers
    // on both ends, which is what a decline curve actually needs to be read.
    const wpPath = m.warPath || [];
    const warTrend = miniTrendSVG(
      wpPath.map((w, i) => ({ v: w, t: `${cls.class_year + i}: ${formatMetric(w, "war")} bWAR` })),
      { w: 300, h: 66, color: "var(--accent-cyan)", fmt: v => formatMetric(v, "war"),
        style: "display:block;width:100%;max-width:340px;height:auto;margin:2px 0 0;",
        xFirst: String(cls.class_year), xLast: String(cls.class_year + wpPath.length - 1),
        aria: `Projected bWAR by season, ${cls.class_year} through ${cls.class_year + wpPath.length - 1}` });
    const comps = (m.comps || []).map(c => `<tr><td>${esc(c.name)}</td><td>${c.yr}</td><td>${teamLogo(c.to)}${esc(c.to || "")}</td><td>${c.years ?? "?"}y / ${c.guar ? money(c.guar) : "?"}</td></tr>`).join("");
    const fits = (m.fits || []).map(f =>
      `<span class="chip" title="need ${f.need} / window ${f.window} / afford ${f.afford} / park ${f.park} / behavior ${f.behavior}${f.blockedBy ? " - blocked by " + esc(blockedText(f.blockedBy)) : ""}">${teamLogo(f.org)}${f.org}${f.blockedBy ? "*" : ""} &middot; ${f.fit}</span>`).join(" ");
    const signedBlock = m.status === "signed" ? `
      <h3>Signed</h3>
      <p>${teamLogo(m.from)}${esc(m.from || "")} &rarr; <strong>${teamLogo(m.signedTo)}${esc(m.signedTo || "")}</strong> &middot;
      ${m.signedMilb ? "MiLB deal" : `${m.signedYears ?? "?"}y / ${money(m.signedGuar)} (${money(m.signedAav)} AAV)`}
      ${m.signedDate ? `<span class="fa-sub"> &middot; first seen ${m.signedDate}</span>` : ""}
      ${(m.projGuar != null && m.signedGuar != null && !m.signedMilb) ? `<br>vs predicted ${m.projYears}y / ${money(m.projGuar)} - miss ${formatMetric(((m.signedGuarNpv ?? m.signedGuar) - m.projGuar) / 1e6, "surplusM")}; Deal+ at the actual price ${Math.round(100 * m.rational / (m.signedGuarNpv ?? m.signedGuar))}` : ""}</p>` : "";
    const arcBlock = m.fvArc ? `
      <h3>Prospect to payday</h3>
      <div class="fa-arc">${_fvArcSvg(m.fvArc)}</div>
      <p class="fa-note">Consensus-FV history from his run as a tracked PROSPX prospect
      (${m.fvArc[0][0]} &rarr; ${m.fvArc[m.fvArc.length - 1][0]}), ending at today's
      ${m.projGuar != null ? money(m.projGuar) + " predicted guarantee" : "constructed class row"} &middot;
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
      ${(m.surplusP10 != null && m.surplusP90 != null) ? `<p class="fa-note" title="Rational value of the floor/ceiling WAR paths minus the predicted price - the probability-bucketed read on the deal">Surplus range (floor &rarr; ceiling): ${surplusSpan(m.surplusP10)} &rarr; ${surplusSpan(m.surplusP90)} around a mean of ${surplusSpan(m.surplus)}</p>` : ""}`;
    const seasonPanel = `
      ${yearRows ? `<h3>Season-by-season projection</h3>
      <table class="detail-table fa-year-table">
      <thead><tr><th>Season</th><th>Age</th><th title="P10 of the Gate-1 probability bucket, decayed along the aging curves">Floor</th><th>Mean</th><th title="P90 of the Gate-1 probability bucket, decayed along the aging curves">Ceiling</th><th><span data-gl="winter_dpw">$/WAR</span></th></tr></thead>
      <tbody>${yearRows}</tbody></table>` : ""}
      ${warTrend ? `<div class="fa-war-trend" title="Projected bWAR by season, labelled at both ends (hover any point for its season)">${warTrend}</div>` : ""}
      ${wp ? `<div class="fa-warpath" title="Aging-curve-decayed projected bWAR by season (hover bars for the floor/ceiling band)">${wp}</div>` : ""}
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
          <div class="mlbp-name">${teamLogo(m.from)}<h2>${esc(m.name)}</h2></div>
          <div class="fa-sub">${esc(m.pos || "")} &middot; ${m.age != null ? "age " + Math.floor(m.age) : "?"} &middot; ${esc(m.from || "")}${handLabel(m) ? " &middot; " + esc(handLabel(m)) : ""} &middot; ${statusChip(m)}</div>
          <div style="margin-top:8px;"><button class="chip egfx-chip" id="fa-player-gfx" title="Generate a shareable graphic (theme-aware)"><span class="egfx-chip-glyph" aria-hidden="true">&#9636;</span>Generate GFX</button></div>
        </div>
        <div class="mlbp-tiles">
          ${m.projGuar != null ? `<div class="mlbp-tile"><span class="mlbp-tile-label">projected</span><span class="mlbp-tile-val">${m.projYears != null ? m.projYears + "y" : "?"} / ${money(m.projGuar)}</span></div>` : ""}
          ${m.projAav != null ? `<div class="mlbp-tile"><span class="mlbp-tile-label">proj AAV</span><span class="mlbp-tile-val">${money(m.projAav)}</span></div>` : ""}
          ${m.dealPlus != null ? `<div class="mlbp-tile"><span class="mlbp-tile-label">Deal+</span><span class="mlbp-tile-val">${Math.round(m.dealPlus)}</span></div>` : ""}
        </div>
      </div>
      ${m.thinPlatform ? `<div class="fa-cba-note">&#9888; ${esc(m.thinPlatform)} - the projection, and every number priced off it, is low-confidence.</div>` : ""}
      ${m.note ? `<div class="fa-cba-note">&#8251; ${esc(m.note)}</div>` : ""}
      ${strip}${tabBody}`;
    bindFaCardTabs(rows, m);
    // hub strip + headshot (cross-module identity via player_links.json) -
    // lazy, never blocks the card paint; FA rows carry no mlbam locally.
    if (window.EEPHUS_HUB) {
      window.EEPHUS_HUB.links().then(L => {
        const row = L && (L.byKey || {})[m.key];
        // Fill the stat line FIRST: it is the only block here that is content
        // rather than chrome, and a hub-strip/headshot failure must not take it
        // down with it.
        if (row && row.mlbam) fillCurrentLine(row.mlbam);
        const hub = document.getElementById("fa-hub");
        if (hub && row) hub.innerHTML = window.EEPHUS_HUB.stripHTML(row, "fa");
        const ph = document.getElementById("fa-hero-photo");
        if (ph && row && row.mlbam) {
          // .mlbp-headshot is 96x96.
          ph.outerHTML = `<img class="mlbp-headshot" src="${faHeadshotURL(row.mlbam, 96)}" alt="" onerror="this.style.visibility='hidden'">`;
        }
        const btn = document.getElementById("fa-player-gfx");
        if (btn) btn.onclick = () => sharePlayerCard(m, row);
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
  // = league average hitter), SEM+/REM+ and FIP are the run-prevention numbers,
  // and season bWAR lives on the MLB player card rather than the leaderboards.
  // Inventing either number to fill the row would be worse than its absence.
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
        + cell("HEM+", line.hem, "HEM+ - offensive-rate skill index, 100 = league-average hitter. This site does not compute wRC+.")
        + cell("Tier", line.tier ? esc(line.tier) : null);
    } else {
      tiles = cell("IP", line.ip == null ? null : Number(line.ip).toFixed(1))
        + cell("ERA", line.era == null ? null : Number(line.era).toFixed(2))
        + cell("FIP", line.fip == null ? null : Number(line.fip).toFixed(2), "FIP - this site does not compute xFIP.")
        + cell("K%", pct(line.kPct)) + cell("BB%", pct(line.bbPct))
        + cell(line.side === "sp" ? "SEM+" : "REM+", line.side === "sp" ? line.sem : line.rem,
               line.side === "sp" ? "SEM+ - starter run-prevention skill index, 100 = league average."
                                  : "REM+ - reliever skill index, 100 = league average.");
    }
    if (!tiles) return "";
    const qual = line.qual === false
      ? ' <span class="fa-sub">(below the qualifying threshold - the rate stats are shrunk toward league average)</span>' : "";
    return `<h3>${esc(meta.season || "")} season to date</h3>
      <div class="mlbp-tiles fa-current-tiles">${tiles}</div>
      <p class="fa-note">Lifted verbatim from the eephus.io MLB leaderboards${meta.asOf ? `, data as of ${esc(meta.asOf)}` : ""}.${qual}</p>`;
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
        : `<h3>${esc((payload && payload.season) || "")} season to date</h3><p class="fa-note">No current-season line: this player is not on the MLB leaderboards for the season (injured, not yet on a roster, or below the leaderboard's minimum playing time).</p>`;
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
      caption: "predicted market (projGuarantee) vs rational value - two numbers, never conflated · gate-validated, ex-ante",
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
      ? bb.map(b => `<span class="fa-block fa-block-${b.t}" title="${b.t === "mlb" ? "MLB incumbent already producing at the slot the signing would displace" : "PROSPX prospect (FV ≥ 50, near ETA)"}">${esc(b.n)}<i>${b.t === "mlb" ? "MLB" : "PX"}</i></span>`).join(" ")
      : EM_DASH;
    const body = list.map(({ m, f }) => `<tr>
        <td><strong>${playerLink(m)}</strong> <span class="fa-sub">${esc(m.pos || "")} &middot; ${m.age != null ? Math.floor(m.age) : "?"}</span></td>
        <td><strong>${f.fit.toFixed(2)}</strong></td>
        <td>${cbar(f.need, "need")}</td><td>${cbar(f.window, "window")}</td><td>${cbar(f.afford, "afford")}</td><td>${cbar(f.park, "park")}</td><td>${cbar(f.behavior, "behavior")}</td>
        <td>${blockedCell(f.blockedBy)}</td>
        <td>${m.projGuar != null ? `${m.projYears}y / ${money(m.projGuar)}` : EM_DASH}</td>
        <td>${verdictChip(m)}</td>
      </tr>`).join("");
    const blockedLine = (t.blocked || []).length
      ? `<div class="fa-note" title="Positions this club is NOT shopping at - the needs matrix found a blocker. MLB = a contracted incumbent producing at the slot a signing would displace; PX = a near-ETA PROSPX prospect (FV ≥ 50).">Not buying: ${t.blocked.map(b =>
          `<span class="fa-block fa-block-${b.t}">${esc(b.pos)} - ${esc(b.n)}${b.w != null ? ` (${formatMetric(b.w, "war")} WAR)` : ""}<i>${b.t === "mlb" ? "MLB" : "PX"}</i></span>`).join(" ")}</div>` : "";
    const fitsGfx = (window.EEPHUS_GFX && list.length)
      ? ` &middot; ${window.EEPHUS_GFX.chipHTML("fa-fits-gfx")}` : "";
    const fitsMain = `${blockedLine}
      <table class="detail-table fa-fits-table">
      <thead><tr><th>Player</th><th>Fit</th><th title="Displacement WAR gap at the position (CAN they upgrade here)">Need</th><th title="Marginal playoff leverage at the club's baseline wins">Window</th><th title="CBT space vs the predicted AAV - habitual taxpayers keep a documented floor">Afford</th><th title="Park factor alignment (deliberately the smallest weight - a tiebreaker, not a driver)">Park</th><th title="WILL they spend: biggest deal ever vs this price, recent 3-winter outlay, $100M-deal participation">Behavior</th><th title="WHO blocks the position: PX = PROSPX prospect (near ETA), MLB = contracted incumbent producing at the displaced slot">Blocked by</th><th>Predicted</th><th>Verdict</th></tr></thead>
      <tbody>${body || `<tr><td colspan="10">No scored fits for ${state.team} in this class.</td></tr>`}</tbody></table>`;
    rows.innerHTML = `<div class="filter-bar"><span class="filter-label">Team</span>${chips}</div>
      <div class="newsprint-eyebrow" style="margin-top:2px;"><span class="newsprint-eyebrow-label">${teamLogo(state.team)}${state.team} fits</span>
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

  function renderArchive(rows) {
    const arc = D.fa_archive;
    if (!arc || !arc.winters || !arc.winters.length) {
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
        <td>${esc(s.from || "")} &rarr; ${teamLogo(s.to)}${esc(s.to || "")}</td>
        <td>${s.years ?? EM_DASH}</td>
        <td>${s.milb ? "MiLB deal" : money(s.guar)}</td>
        <td>${money(s.aav)}</td>
        <td title="Realized bWAR over the contract's elapsed seasons">${s.warTd != null ? formatMetric(s.warTd, "war") : EM_DASH}</td>
        <td title="Realized surplus to date: WAR delivered x that season's estimated $/WAR minus prorated money paid">${s.surplusTd != null ? formatMetric(s.surplusTd / 1e6, "surplusM") : EM_DASH}</td>
        <td>${s.done ? "complete" : (s.warTd != null ? "running" : EM_DASH)}</td>
      </tr>`).join("");
    const arcGfx = (window.EEPHUS_GFX && w.signings.length)
      ? ` &middot; ${window.EEPHUS_GFX.chipHTML("fa-archive-gfx")}` : "";
    const archiveMain = `<table class="detail-table">
      <thead><tr><th>Player</th><th title="From = the club holding his rights AT signing - a midseason rental shows the acquiring club, not the team he opened the year with.">From &rarr; To</th><th>Yrs</th><th>Guarantee</th><th>AAV</th><th>WAR to date</th><th>Surplus to date</th><th>Status</th></tr></thead>
      <tbody>${body}</tbody></table>`;
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
      rows.innerHTML = `<div class="state-message">Model evaluation artifacts not exported yet.</div>`;
      return;
    }
    const g1 = meta.gate1, g2 = meta.gate2;
    const pooledRows = (pooled, fmt) => Object.entries(pooled).map(([k, v]) =>
      `<tr><td>${esc(k)}</td><td>${fmt(v.mae_model)}</td><td>${fmt(v.mae_base)}</td><td>${v.n}</td><td>${v.mae_model < v.mae_base ? "&#10003; beats baseline" : "&#10007; behind baseline"}</td></tr>`).join("");
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
      <span class="newsprint-eyebrow-meta">both hard gates, rendered verbatim from the committed eval artifacts, misses included &middot; ${meta.cba ? meta.cba.unverified_records + " curated CBA records pending owner verification" : ""}</span></div>
      ${g1 ? `<h3>Gate 1 - projection engine (${g1.pass ? "PASSED" : "FAILING"})</h3>
      <div class="fa-note">train &le; N&minus;1, predict N, ten held-out seasons ${g1.targets ? g1.targets.join(", ") : ""} &middot; P10&ndash;P90 coverage ${g1.coverage_p10_p90 != null ? g1.coverage_p10_p90.toFixed(3) : "?"} (target 0.75&ndash;0.85)</div>
      <table class="detail-table"><thead><tr><th>Metric</th><th>Model MAE</th><th>Naive baseline</th><th>n</th><th>Verdict</th></tr></thead>
      <tbody>${pooledRows(g1.pooled, v => v == null ? EM_DASH : v.toFixed(3))}</tbody></table>` : ""}
      ${g2 ? `<h3>Gate 2 - market model (${g2.pass ? "PASSED" : "FAILING"})</h3>
      <div class="fa-note">forward-chained winters ${g2.test_winters ? g2.test_winters.join(", ") : ""} vs nearest-comps baseline &middot; guarantee/AAV in $M</div>
      <table class="detail-table"><thead><tr><th>Metric</th><th>Model MAE</th><th>Comps baseline</th><th>n</th><th>Verdict</th></tr></thead>
      <tbody>${pooledRows(g2.pooled, v => v == null ? EM_DASH : v.toFixed(2))}</tbody></table>
      ${g2.pooled_by_pos_group ? `
      <h3>Where the model is systematically wrong</h3>
      <div class="fa-note">MAE says how far off the model is; BIAS says which
        way. A negative bias means the model UNDER-prices that group on average,
        so the error is not noise, it is a lean. Positive means it over-prices.
        This block was exported for a while before anything rendered it.</div>
      <table class="detail-table"><thead><tr><th>Group</th><th>Model MAE</th>
        <th>Model bias</th><th>Baseline bias</th><th>n</th><th>Lean</th></tr></thead>
      <tbody>${Object.entries(g2.pooled_by_pos_group).map(([k, v]) => {
        const b = v.bias_model;
        const lean = b == null ? EM_DASH
          : Math.abs(b) < 0.25 ? "no material lean"
          // Plain magnitude, NOT formatMetric: that helper prepends a sign for
          // "rate", which rendered "under-prices by +1.53M" and put a plus sign
          // directly after the word telling you the error is negative.
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
      <h3>What changed, and what it cost</h3>
      <div class="fa-note">${esc(meta.war_input_divergence.before_after.change)},
        shipped ${esc(meta.war_input_divergence.before_after.shipped)}. Same rows
        on both sides. ${esc(meta.war_input_divergence.before_after.note || "")}</div>
      <table class="detail-table"><thead><tr><th>Metric</th><th>Before</th>
        <th>After</th><th>Change</th></tr></thead>
      <tbody>${(meta.war_input_divergence.before_after.rows || []).map(r => {
        const d = r.after - r.before;
        const good = r.better === "lower" ? d < 0 : d > 0;
        return `<tr><td>${esc(r.metric)} <span class="proj-dim">${esc(r.unit)}</span></td>
          <td>${r.before.toFixed(3)}</td><td>${r.after.toFixed(3)}</td>
          <td>${(d > 0 ? "+" : "") + d.toFixed(3)} ${good ? "better" : "worse"}</td></tr>`;
      }).join("")}</tbody></table>` : ""}
      <h3>Biggest misses (published, not hidden)</h3>
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
