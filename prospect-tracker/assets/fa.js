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
    value: ["VALUE", "Projected to be UNDERPAID - rational value runs well past the predicted price (Deal+ in the corpus top tercile, ≥185)."],
    market: ["MARKET", "Priced about right - rational value and predicted price within the corpus middle tercile (Deal+ 85–185)."],
    overpay: ["OVERPAY", "Projected to be OVERPAID - predicted price runs past rational value (Deal+ in the corpus bottom tercile, <85)."],
  };
  function verdictChip(m) {
    const v = VERDICT_META[m.verdict];
    if (!v) return EM_DASH;
    return `<span class="fa-verdict fa-verdict-${m.verdict}" data-gl="deal_plus" title="${v[1]} Underlying Deal+ ${m.dealPlus ?? "?"} (100 × rational / predicted price).">${v[0]}</span>`;
  }
  function surplusSpan(usd, p10, p90) {
    if (usd == null) return EM_DASH;
    const band = (p10 != null && p90 != null)
      ? ` title="Floor/ceiling surplus from the P10/P90 WAR paths: ${formatMetric(p10 / 1e6, "surplusM")} … ${formatMetric(p90 / 1e6, "surplusM")}"` : "";
    return `<span class="${usd >= 0 ? "fa-pos" : "fa-neg"}"${band}>${formatMetric(usd / 1e6, "surplusM")}</span>`;
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
    const curYear = (D.fa_class && D.fa_class.class_year) || new Date().getFullYear() + 1;
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
      rows.innerHTML = `<div class="state-message is-error">Free-agency data unavailable
        (${esc(String(e.message || e))}). Run <code>python fa_export.py</code> to regenerate
        <code>data/fa_*.json</code>.</div>`;
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
      ? `<div class="fa-cba-note">&#9888; CBA rules past 2026-12-01 are <span data-gl="cba_carry_forward">carried forward</span> &mdash; thresholds and QO values for this winter are NOT yet collectively bargained.</div>`
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

  function playerLink(m) {
    return `<a href="#player=${encodeURIComponent(m.key || "")}" class="fa-player-link"><span class="fa-row-photo" data-photo-key="${esc(m.key || "")}"></span><strong>${esc(m.name)}</strong></a>`;
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
          el.innerHTML = `<img class="fa-row-headshot" loading="lazy" src="https://img.mlbstatic.com/mlb-photos/image/upload/d_people:generic:headshot:67:current.png/w_72,q_auto:best/v1/people/${row.mlbam}/headshot/67/current" alt="" onerror="this.remove()">`;
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
    if (!src || !Object.keys(src).length) return "";
    const stale = d => (Date.now() - new Date(d + "T00:00:00").getTime()) / 864e5 > 14;
    const parts = Object.entries(src).map(([k, d]) =>
      `${k} ${d}${stale(d) ? ` <span class="fa-stale" title="${k} last fetched ${d} - more than 14 days old. Re-run the FA pipeline.">&#9888; stale</span>` : ""}`);
    return `<div class="fa-note fa-sources" title="MAX(fetched_at) per source table - when each input was last pulled, not when the page was built.">sources: ${parts.join(" &middot; ")}</div>`;
  }

  // ---- Share card - canvas-native PNG of the board's top 10 -----------------
  // Drawn by hand (no html2canvas: it can't resolve CSS var(), per the PROSPX
  // GFX builder's literal-stops precedent), so the card is deterministic in
  // both themes. Token colors are read from the live computed style.
  function _tok(name, fallback) {
    const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    return v || fallback;
  }

  function downloadShareCard(cls) {
    const dark = document.documentElement.getAttribute("data-theme") === "dark";
    const W = 1200, H = 675, PAD = 48;
    const c = document.createElement("canvas");
    c.width = W; c.height = H;
    const g = c.getContext("2d");
    const bg = _tok("--bg-primary", dark ? "#101014" : "#F6F1E4");
    const fg = _tok("--text-primary", dark ? "#ECEEF2" : "#0F1B2D");
    const sub = _tok("--text-tertiary", dark ? "#7C808A" : "#706B5C");
    const line = _tok("--border", dark ? "#2B2B31" : "#C9C1AE");
    const MONO = '"MS Gothic","Osaka-Mono","Roboto Mono",monospace';
    g.fillStyle = bg; g.fillRect(0, 0, W, H);
    // iridescent rule - literal stops per theme (canvas can't read var())
    const ramp = g.createLinearGradient(PAD, 0, W - PAD, 0);
    (dark
      ? [[0, "#00D9FF"], [0.3, "#B47CFF"], [0.55, "#FF4FD8"], [0.78, "#FFD700"], [1, "#4FFF9E"]]
      : [[0, "#B91C1C"], [0.35, "#C9A227"], [0.65, "#1F7A3A"], [1, "#0E2B4D"]]
    ).forEach(([s, col]) => ramp.addColorStop(s, col));
    g.fillStyle = ramp; g.fillRect(PAD, 86, W - 2 * PAD, 3);
    g.fillStyle = fg;
    g.font = `700 34px ${MONO}`;
    g.fillText(`MLB FREE AGENCY - ${cls.class_year - 1}-${String(cls.class_year).slice(2)} CLASS BOARD`, PAD, 60);
    g.fillStyle = sub;
    g.font = `16px ${MONO}`;
    g.fillText(`${cls.n_members} constructed members · ${cls.n_projected} projected · winter $/WAR (ex-ante) ${money(cls.dpw_usd)}`, PAD, 116);
    const cols = [PAD, PAD + 50, PAD + 440, PAD + 610, PAD + 750, PAD + 905, PAD + 1010];
    g.font = `700 14px ${MONO}`;
    ["#", "PLAYER", "projLEN/GUAR", "projAAV", "DEAL WAR", "SURPLUS", "VERDICT"].forEach((h, i) =>
      g.fillText(h, cols[i], 152));
    g.strokeStyle = line; g.beginPath(); g.moveTo(PAD, 162); g.lineTo(W - PAD, 162); g.stroke();
    const top = cls.members.filter(m => m.projGuar != null).slice(0, 10);
    const vcol = { value: dark ? "#4FFF9E" : "#1F7A3A", market: sub, overpay: dark ? "#FF6B6B" : "#B91C1C" };
    top.forEach((m, i) => {
      const y = 196 + i * 40;
      g.fillStyle = sub; g.font = `16px ${MONO}`;
      g.fillText(String(i + 1), cols[0], y);
      g.fillStyle = fg; g.font = `700 17px ${MONO}`;
      g.fillText(m.name, cols[1], y);
      const nameW = g.measureText(m.name).width;
      g.fillStyle = sub; g.font = `13px ${MONO}`;
      g.fillText(`${m.pos || ""} · ${m.age != null ? Math.floor(m.age) : "?"} · ${m.from || ""}${m.thinPlatform ? " · ⚠ thin platform" : ""}`,
                 cols[1] + nameW + 10, y);
      g.fillStyle = fg; g.font = `16px ${MONO}`;
      g.fillText(`${m.projYears}y / ${money(m.projGuar)}`, cols[2], y);
      g.fillText(money(m.projAav), cols[3], y);
      g.fillText(m.warTotal != null ? m.warTotal.toFixed(1) : " - ", cols[4], y);
      g.fillText(formatMetric(m.surplus / 1e6, "surplusM"), cols[5], y);
      g.fillStyle = vcol[m.verdict] || sub;
      g.fillText((m.verdict || " - ").toUpperCase(), cols[6], y);
    });
    g.fillStyle = sub; g.font = `13px ${MONO}`;
    g.fillText("predicted market (projGuarantee) vs rational value - two numbers, never conflated · both hard gates passed · projections ex-ante",
               PAD, H - 56);
    g.fillStyle = fg; g.font = `700 16px ${MONO}`;
    g.fillText("eephus.io/fa", PAD, H - 28);
    c.toBlob(blob => {
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `fa-class-board-${cls.class_year - 1}-${String(cls.class_year).slice(2)}.png`;
      a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 5000);
    }, "image/png");
  }

  // Blocked-by chips: WHO and WHAT KIND ('prospect' = PROSPX near-ETA,
  // 'mlb' = a contracted incumbent already producing at the slot).
  function blockedText(blockedBy) {
    if (!blockedBy || !blockedBy.length) return "";
    return blockedBy.map(b => `${b.n} (${b.t === "mlb" ? "MLB incumbent" : "prospect"})`).join(", ");
  }

  const boardState = { sort: "projGuar", dir: -1 };

  function renderBoard(rows, cls) {
    const sortKey = boardState.sort;
    const members = cls.members.slice().sort((a, b) => {
      const v = m => m[sortKey] ?? (sortKey === "age" ? 99 : -1e15);
      return boardState.dir * (v(a) > v(b) ? 1 : v(a) < v(b) ? -1 : 0);
    });
    const sHead = (label, key, title) => {
      const on = sortKey === key;
      return `<th class="fa-sort${on ? " is-sorted" : ""}" data-fsort="${key}" title="${esc(title || "Click to sort")}">${label}${on ? (boardState.dir < 0 ? " ▾" : " ▴") : ""}</th>`;
    };
    const head = `<div class="newsprint-eyebrow" style="margin-top:4px;">
      <span class="newsprint-eyebrow-label">2026-27 Class Board</span>
      <span class="newsprint-eyebrow-meta">${cls.members.length} constructed members &middot; ${cls.n_projected} projected &middot; winter $/WAR (ex-ante) ${money(cls.dpw_usd)}, escalating ${((cls.dpw_infl || 0.05) * 100).toFixed(0)}%/yr &middot; <button class="chip" id="fa-gfx-btn" title="Download the top of the board as a PNG share card (theme-aware)">&#8681; share card</button></span>
    </div>`;
    const body = members.map((m, i) => {
      const fits = (m.fits || []).map(f =>
        `<span class="fa-fitorg" title="fit ${f.fit} - need ${f.need} / window ${f.window} / afford ${f.afford} / park ${f.park} / behavior ${f.behavior}${f.blockedBy ? " - blocked by " + esc(blockedText(f.blockedBy)) : ""}">${teamLogo(f.org)}${f.org}${f.blockedBy ? "*" : ""}</span>`).join(" ");
      const comps = (m.comps || []).map(c =>
        `${esc(c.name)} '${String(c.yr).slice(2)} ${c.years || "?"}y/${c.guar ? "$" + (c.guar / 1e6).toFixed(0) + "M" : "?"}`).join("; ");
      const yearsBand = m.projYears != null
        ? `${m.projYears}<span class="fa-band"> (${m.projYearsP10 ?? "?"}&ndash;${m.projYearsP90 ?? "?"})</span>` : EM_DASH;
      const guarBand = m.projGuar != null
        ? `${money(m.projGuar)}<span class="fa-band"> (${money(m.projGuarP10)}&ndash;${money(m.projGuarP90)})</span>` : EM_DASH;
      const dealWar = m.warTotal != null
        ? `${formatMetric(m.warTotal, "war")}<span class="fa-band"> (${formatMetric(m.warTotalP10, "war")}&ndash;${formatMetric(m.warTotalP90, "war")})</span>` : EM_DASH;
      return `<tr${m.projGuar == null || m.status === "option_exercised" ? ' class="fa-dim"' : ""}>
        <td>${i + 1}</td>
        <td>${playerLink(m)}${noteBadge(m)}<span class="fa-sub"> ${esc(m.pos || "")} &middot; ${m.age != null ? Math.floor(m.age) : "?"} &middot; ${teamLogo(m.from)}${esc(m.from || "")}</span>${comps ? `<div class="fa-comps" title="Nearest real historical contracts (never fabricated)">comps: ${comps}</div>` : ""}</td>
        <td>${statusChip(m)}</td>
        <td>${m.warY1 != null ? formatMetric(m.warY1, "war") : EM_DASH}${thinBadge(m)}</td>
        <td title="Projected bWAR over the predicted term (floor–ceiling from the Gate-1 probability buckets)">${dealWar}</td>
        <td>${yearsBand}</td>
        <td>${guarBand}</td>
        <td>${m.projAav != null ? `${money(m.projAav)}<span class="fa-band"> (${money(m.projAavP10)}&ndash;${money(m.projAavP90)})</span>` : EM_DASH}</td>
        <td>${m.rational != null ? money(m.rational) : EM_DASH}</td>
        <td>${surplusSpan(m.surplus, m.surplusP10, m.surplusP90)}</td>
        <td>${verdictChip(m)}</td>
        <td title="* = blocked (hover each club for who's blocking - prospect or MLB incumbent)">${fits || EM_DASH}</td>
      </tr>`;
    }).join("");
    rows.innerHTML = head + `<div class="fa-board-layout"><div class="fa-board-main"><table class="detail-table">
      <thead><tr><th>#</th><th>Player</th><th>Status</th>
      ${sHead(`<span data-gl="war">WAR</span> y1`, "warY1", "Projected year-1 bWAR")}
      ${sHead("Deal WAR", "warTotal", "Projected bWAR over the predicted term, with floor–ceiling buckets")}
      ${sHead(`<span data-gl="m_years">projLength</span>`, "projYears", "Predicted contract length (P10–P90)")}
      ${sHead(`<span data-gl="m_guarantee">projGuarantee</span>`, "projGuar", "Predicted total guarantee (P10–P90)")}
      ${sHead(`<span data-gl="m_aav">projAAV</span>`, "projAav", "Predicted average annual value (P10–P90)")}
      ${sHead(`<span data-gl="rational_value">Rational</span>`, "rational", "Convex-priced NPV of the projected production")}
      ${sHead(`<span data-gl="contract_surplus">Surplus</span>`, "surplus", "Rational value minus predicted price (hover for the floor/ceiling range)")}
      <th><span data-gl="deal_plus">Verdict</span></th>
      <th><span data-gl="fit_components">Fits</span></th></tr></thead>
      <tbody>${body}</tbody></table></div>
      ${boardRail(cls)}</div>`;
    rows.querySelectorAll("[data-fsort]").forEach(h => h.onclick = () => {
      const k = h.dataset.fsort;
      if (boardState.sort === k) boardState.dir = -boardState.dir;
      else { boardState.sort = k; boardState.dir = -1; }
      renderBoard(rows, cls);
      if (window.EEPHUS_GL) window.EEPHUS_GL.wire(rows);
    });
    const gfx = document.getElementById("fa-gfx-btn");
    if (gfx) gfx.onclick = () => downloadShareCard(cls);
    fillRowPhotos(rows);
  }

  // Market-pulse rail beside the board: best values, biggest projected
  // overpays, class supply by position group, the $/WAR trend.
  function boardRail(cls) {
    const proj = cls.members.filter(m => m.projGuar != null);
    const railRow = m => `<div class="fa-rail-row">${teamLogo(m.from)}
      <a class="fa-player-link" href="#player=${encodeURIComponent(m.key || "")}">${esc(m.name)}</a>
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
    const trend = yrs.slice(-6).map(y =>
      `<div class="fa-rail-row"><span>${Number(y) - 1}-${String(y).slice(2)}</span><span class="fa-rail-num">${money(series[y])}</span></div>`).join("");
    const mod = (title, body, tip) => body
      ? `<div class="fa-rail-mod"><div class="fa-rail-head" title="${esc(tip || "")}">${title}</div>${body}</div>` : "";
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
        <span class="newsprint-eyebrow-meta">preseason &mdash; goes live with the first observed event</span></div>
        <div class="state-message">
          <div class="state-message-title">The ${cls.class_year - 1}-${String(cls.class_year).slice(2)} winter hasn't opened</div>
          <div class="state-message-body">Signings, option decisions and qualifying offers land here as the
          daily pipeline first observes them (Spotrac publishes no dates, so every event carries its
          observation stamp). The winter runs in sequence: contract options resolve in the days after
          the World Series, qualifying offers are extended and decided, and then the market opens.
          Until then the Class Board carries the projected market &mdash;
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
      return `<tr><td>${e.date}</td><td><a href="#player=${encodeURIComponent(e.key || "")}" class="fa-player-link"><strong>${esc(e.name || e.key || "")}</strong></a> <span class="fa-sub">${esc(e.pos || "")}</span></td><td>${label}</td></tr>`;
    }).join("");
    const remaining = cls.members.filter(m => m.status !== "signed" && m.status !== "option_exercised" && m.projGuar != null).slice(0, 10);
    rows.innerHTML = `<div class="newsprint-eyebrow"><span class="newsprint-eyebrow-label">Signing Tracker &mdash; live</span>
      <span class="newsprint-eyebrow-meta">${signed.length} of ${cls.n_members} signed &middot; ${money(spent)} guaranteed &middot; ${mae != null ? `running guarantee MAE ${money(mae)} over ${scored.length} scored deals` : "no scored MLB deals yet"} &middot; dates are first-seen stamps</span></div>
      ${sigRows ? `<table class="detail-table">
        <thead><tr><th><span data-gl="first_seen_dates">Seen</span></th><th>Player</th><th>From &rarr; To</th><th>Actual</th><th><span data-gl="m_guarantee">Predicted</span></th><th>&Delta; Guar</th><th><span data-gl="deal_plus">Deal+</span> real</th></tr></thead>
        <tbody>${sigRows}</tbody></table>` : ""}
      ${evRows ? `<h3>Option &amp; QO timeline</h3><table class="detail-table">
        <thead><tr><th>Seen</th><th>Player</th><th>Event</th></tr></thead><tbody>${evRows}</tbody></table>` : ""}
      ${remaining.length ? `<h3>Top of the remaining board</h3><table class="detail-table">
        <thead><tr><th>Player</th><th><span data-gl="m_years">projLength</span></th><th><span data-gl="m_guarantee">projGuarantee</span></th><th><span data-gl="m_aav">projAAV</span></th><th>Verdict</th></tr></thead>
        <tbody>${remaining.map(m => `<tr><td>${playerLink(m)} <span class="fa-sub">${esc(m.pos || "")}</span></td>
          <td>${m.projYears}</td><td>${money(m.projGuar)}</td><td>${money(m.projAav)}</td><td>${verdictChip(m)}</td></tr>`).join("")}</tbody></table>` : ""}`;
  }

  // ---- FA player card (#player=<key>) ----------------------------------------
  function _fvArcSvg(arc) {
    // Tiny inline FV sparkline (20–80 scale). Pure presentation - the points
    // are the exported consensus-FV change history, nothing interpolated.
    const w = 280, h = 56, pad = 4;
    const vals = arc.map(p => p[1]);
    const lo = Math.min(35, ...vals) - 2, hi = Math.max(55, ...vals) + 2;
    const x = i => pad + (w - 2 * pad) * (arc.length === 1 ? 0 : i / (arc.length - 1));
    const y = v => h - pad - (h - 2 * pad) * (v - lo) / (hi - lo);
    const pts = arc.map((p, i) => `${x(i).toFixed(1)},${y(p[1]).toFixed(1)}`).join(" ");
    return `<svg viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" role="img" aria-label="Consensus FV history">
      <polyline points="${pts}" fill="none" stroke="currentColor" stroke-width="1.5"/>
      ${arc.map((p, i) => `<circle cx="${x(i).toFixed(1)}" cy="${y(p[1]).toFixed(1)}" r="2"><title>${p[0]} &middot; FV ${p[1]}</title></circle>`).join("")}
    </svg>`;
  }

  function renderPlayer(rows, cls, key) {
    const m = cls.members.find(x => x.key === key);
    if (!m) {
      rows.innerHTML = `<div class="state-message">No class member &ldquo;${esc(key)}&rdquo;. <a href="#view=board">Back to the board</a>.</div>`;
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
    const comps = (m.comps || []).map(c => `<tr><td>${esc(c.name)}</td><td>${c.yr}</td><td>${teamLogo(c.to)}${esc(c.to || "")}</td><td>${c.years ?? "?"}y / ${c.guar ? money(c.guar) : "?"}</td></tr>`).join("");
    const fits = (m.fits || []).map(f =>
      `<span class="chip" title="need ${f.need} / window ${f.window} / afford ${f.afford} / park ${f.park} / behavior ${f.behavior}${f.blockedBy ? " - blocked by " + esc(blockedText(f.blockedBy)) : ""}">${teamLogo(f.org)}${f.org}${f.blockedBy ? "*" : ""} &middot; ${f.fit}</span>`).join(" ");
    const signedBlock = m.status === "signed" ? `
      <h3>Signed</h3>
      <p>${teamLogo(m.from)}${esc(m.from || "")} &rarr; <strong>${teamLogo(m.signedTo)}${esc(m.signedTo || "")}</strong> &middot;
      ${m.signedMilb ? "MiLB deal" : `${m.signedYears ?? "?"}y / ${money(m.signedGuar)} (${money(m.signedAav)} AAV)`}
      ${m.signedDate ? `<span class="fa-sub"> &middot; first seen ${m.signedDate}</span>` : ""}
      ${(m.projGuar != null && m.signedGuar != null && !m.signedMilb) ? `<br>vs predicted ${m.projYears}y / ${money(m.projGuar)} &mdash; miss ${formatMetric((m.signedGuar - m.projGuar) / 1e6, "surplusM")}; Deal+ at the actual price ${Math.round(100 * m.rational / m.signedGuar)}` : ""}</p>` : "";
    const arcBlock = m.fvArc ? `
      <h3>Prospect to payday</h3>
      <div class="fa-arc">${_fvArcSvg(m.fvArc)}</div>
      <p class="fa-note">Consensus-FV history from his run as a tracked PROSPX prospect
      (${m.fvArc[0][0]} &rarr; ${m.fvArc[m.fvArc.length - 1][0]}), ending at today's
      ${m.projGuar != null ? money(m.projGuar) + " predicted guarantee" : "constructed class row"} &middot;
      <a href="/prospx/#player=${encodeURIComponent(m.key)}">full prospect page &rarr;</a></p>` : "";
    rows.innerHTML = `
      <p><a href="#view=board">&larr; Class Board</a></p>
      <div id="fa-hub"></div>
      <div class="mlbp-hero" id="fa-player-hero">
        <span id="fa-hero-photo"></span>
        <div class="mlbp-hero-main">
          <div class="mlbp-name">${teamLogo(m.from)}<h2>${esc(m.name)}</h2></div>
          <div class="fa-sub">${esc(m.pos || "")} &middot; ${m.age != null ? "age " + Math.floor(m.age) : "?"} &middot; ${esc(m.from || "")} &middot; ${statusChip(m)}</div>
          <div style="margin-top:8px;"><button class="chip" id="fa-player-gfx" title="Download this market card as a PNG share card (theme-aware)">&#8681; share card</button></div>
        </div>
        <div class="mlbp-tiles">
          ${m.projGuar != null ? `<div class="mlbp-tile"><span class="mlbp-tile-label">projected</span><span class="mlbp-tile-val">${m.projYears != null ? m.projYears + "y" : "?"} / ${money(m.projGuar)}</span></div>` : ""}
          ${m.projAav != null ? `<div class="mlbp-tile"><span class="mlbp-tile-label">proj AAV</span><span class="mlbp-tile-val">${money(m.projAav)}</span></div>` : ""}
          ${m.dealPlus != null ? `<div class="mlbp-tile"><span class="mlbp-tile-label">Deal+</span><span class="mlbp-tile-val">${Math.round(m.dealPlus)}</span></div>` : ""}
        </div>
      </div>
      ${m.thinPlatform ? `<div class="fa-cba-note">&#9888; ${esc(m.thinPlatform)} &mdash; the projection, and every number priced off it, is low-confidence.</div>` : ""}
      ${m.note ? `<div class="fa-cba-note">&#8251; ${esc(m.note)}</div>` : ""}
      ${signedBlock}
      <h3>Predicted market</h3>
      <table class="detail-table"><thead><tr><th><span data-gl="m_years">projLength</span></th><th><span data-gl="m_guarantee">projGuarantee</span></th><th><span data-gl="m_aav">projAAV</span></th><th>Deal <span data-gl="war">WAR</span></th><th><span data-gl="rational_value">Rational</span></th><th><span data-gl="contract_surplus">Surplus</span></th><th><span data-gl="deal_plus">Verdict</span></th></tr></thead>
      <tbody><tr>
        <td>${band(m.projYears, m.projYearsP10, m.projYearsP90, v => v ?? "?")}</td>
        <td>${band(m.projGuar, m.projGuarP10, m.projGuarP90, money)}</td>
        <td>${band(m.projAav, m.projAavP10, m.projAavP90, money)}</td>
        <td>${band(m.warTotal, m.warTotalP10, m.warTotalP90, v => v == null ? "?" : formatMetric(v, "war"))}</td>
        <td>${m.rational != null ? money(m.rational) : EM_DASH}</td>
        <td>${surplusSpan(m.surplus, m.surplusP10, m.surplusP90)}</td>
        <td>${verdictChip(m)}</td>
      </tr></tbody></table>
      ${(m.surplusP10 != null && m.surplusP90 != null) ? `<p class="fa-note" title="Rational value of the floor/ceiling WAR paths minus the predicted price - the probability-bucketed read on the deal">Surplus range (floor &rarr; ceiling): ${surplusSpan(m.surplusP10)} &rarr; ${surplusSpan(m.surplusP90)} around a mean of ${surplusSpan(m.surplus)}</p>` : ""}
      ${yearRows ? `<h3>Season-by-season projection</h3>
      <table class="detail-table fa-year-table">
      <thead><tr><th>Season</th><th>Age</th><th title="P10 of the Gate-1 probability bucket, decayed along the aging curves">Floor</th><th>Mean</th><th title="P90 of the Gate-1 probability bucket, decayed along the aging curves">Ceiling</th><th><span data-gl="winter_dpw">$/WAR</span></th></tr></thead>
      <tbody>${yearRows}</tbody></table>` : ""}
      ${wp ? `<div class="fa-warpath" title="Aging-curve-decayed projected bWAR by season (hover bars for the floor/ceiling band)">${wp}</div>` : ""}
      ${arcBlock}
      ${comps ? `<h3>Nearest real comps</h3><table class="detail-table">
        <thead><tr><th>Player</th><th>Winter</th><th>To</th><th>Deal</th></tr></thead><tbody>${comps}</tbody></table>` : ""}
      ${fits ? `<h3>Top team fits</h3><div class="fa-fitchips">${fits}</div>` : ""}`;
    // hub strip + headshot (cross-module identity via player_links.json) -
    // lazy, never blocks the card paint; FA rows carry no mlbam locally.
    if (window.EEPHUS_HUB) {
      window.EEPHUS_HUB.links().then(L => {
        const row = L && (L.byKey || {})[m.key];
        const hub = document.getElementById("fa-hub");
        if (hub && row) hub.innerHTML = window.EEPHUS_HUB.stripHTML(row, "fa");
        const ph = document.getElementById("fa-hero-photo");
        if (ph && row && row.mlbam) {
          ph.outerHTML = `<img class="mlbp-headshot" src="https://img.mlbstatic.com/mlb-photos/image/upload/d_people:generic:headshot:67:current.png/w_240,q_auto:best/v1/people/${row.mlbam}/headshot/67/current" alt="" onerror="this.style.visibility='hidden'">`;
        }
        const btn = document.getElementById("fa-player-gfx");
        if (btn) btn.onclick = () => sharePlayerCard(m, row);
      });
    }
  }

  // Unified per-player share card (EEPHUS_HUB canvas template) - the FA
  // module's data priorities: the predicted market up top, rational vs
  // surplus + comps as the body.
  function sharePlayerCard(m, linkRow) {
    const tiles = [];
    if (m.projGuar != null) tiles.push({ label: "projected", value: `${m.projYears != null ? m.projYears + "y/" : ""}${money(m.projGuar)}` });
    if (m.projAav != null) tiles.push({ label: "proj AAV", value: money(m.projAav) });
    if (m.dealPlus != null) tiles.push({ label: "Deal+", value: String(Math.round(m.dealPlus)) });
    if (m.warTotal != null) tiles.push({ label: "deal WAR", value: m.warTotal.toFixed(1) });
    const sections = [{
      title: "Predicted market vs rational value",
      rows: [
        ["projGuarantee", `${money(m.projGuar)}${m.projGuarP10 != null ? `  (${money(m.projGuarP10)}-${money(m.projGuarP90)})` : ""}`],
        ["projAAV", `${money(m.projAav)}${m.projAavP10 != null ? `  (${money(m.projAavP10)}-${money(m.projAavP90)})` : ""}`],
        ["rational value", m.rational != null ? money(m.rational) : " - "],
        ["contract surplus", m.surplus != null ? money(m.surplus) : " - "],
        ["verdict", (m.verdict || " - ").toUpperCase()],
        m.prevAav != null ? ["prior AAV", money(m.prevAav)] : null,
      ].filter(Boolean),
    }];
    const comps = (m.comps || []).slice(0, 5);
    if (comps.length) {
      sections.push({ title: "Nearest real comps",
        rows: comps.map(c => [`${c.name || "?"}${c.yr ? ` '${String(c.yr).slice(2)}` : ""}`,
          `${c.years != null ? c.years + "y / " : ""}${c.guar != null ? money(c.guar) : "-"}${c.to ? `  ${c.to}` : ""}`]) });
    }
    window.EEPHUS_HUB.shareCard({
      module: "MLB Free Agency",
      accentToken: "--accent-green",
      name: m.name,
      meta: `${m.pos || ""} · ${m.age != null ? "age " + Math.floor(m.age) : "?"} · ${m.from || ""}`,
      sub: m.verdict ? `verdict: ${String(m.verdict).toUpperCase()}` : "",
      headshotURL: linkRow && linkRow.mlbam
        ? `https://img.mlbstatic.com/mlb-photos/image/upload/d_people:generic:headshot:67:current.png/w_240,q_auto:best/v1/people/${linkRow.mlbam}/headshot/67/current` : null,
      tiles, sections,
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
    rows.innerHTML = `<div class="filter-bar"><span class="filter-label">Team</span>${chips}</div>
      <div class="newsprint-eyebrow" style="margin-top:2px;"><span class="newsprint-eyebrow-label">${teamLogo(state.team)}${state.team} fits</span>
      <span class="newsprint-eyebrow-meta">CBT payroll ${money(t.taxPayroll ?? t.committed)} &middot; tax space ${t.space != null ? formatMetric(t.space / 1e6, "surplusM") : EM_DASH}${t.payor ? ` &middot; ${esc(t.payor)}` : ""} &middot; baseline ${t.baseWins ?? "?"}w (contracted core) &middot; biggest deal ever ${money(t.maxGuar)} &middot; last-3-winter outlay ${money(t.recentSpend)}</span></div>
      ${blockedLine}
      <table class="detail-table fa-fits-table">
      <thead><tr><th>Player</th><th>Fit</th><th title="Displacement WAR gap at the position (CAN they upgrade here)">Need</th><th title="Marginal playoff leverage at the club's baseline wins">Window</th><th title="CBT space vs the predicted AAV - habitual taxpayers keep a documented floor">Afford</th><th title="Park factor alignment (deliberately the smallest weight - a tiebreaker, not a driver)">Park</th><th title="WILL they spend: biggest deal ever vs this price, recent 3-winter outlay, $100M-deal participation">Behavior</th><th title="WHO blocks the position: PX = PROSPX prospect (near ETA), MLB = contracted incumbent producing at the displaced slot">Blocked by</th><th>Predicted</th><th>Verdict</th></tr></thead>
      <tbody>${body || `<tr><td colspan="10">No scored fits for ${state.team} in this class.</td></tr>`}</tbody></table>`;
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
        <td>${esc(s.from || "")} &rarr; ${teamLogo(s.to)}${esc(s.to || "")}</td>
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
      <thead><tr><th>Player</th><th title="From = the club holding his rights AT signing - a midseason rental shows the acquiring club, not the team he opened the year with.">From &rarr; To</th><th>Yrs</th><th>Guarantee</th><th>AAV</th><th>WAR to date</th><th>Surplus to date</th><th>Status</th></tr></thead>
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
