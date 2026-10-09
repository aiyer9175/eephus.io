/* Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
 * Unauthorized copying of this file, via any medium is strictly prohibited
 * Proprietary and confidential
 * Written by Noah J. Dengler (@ARKNDJL), 2026 */

// =============================================================================
// eephus.io - the $/WAR by winter detail view (/fa/#view=dpw)
// =============================================================================
// The board rail carries a 220x74 sparkline of one number per winter. This is
// what that number is made of, and it is a SEPARATE module on purpose: assets
// /fa.js owns the class board and knows nothing about this view, so this file
// mounts its own section, hides #fa-rows while the hash says view=dpw, and
// restores it on the way out. Nothing here writes to fa.js state.
//
// TWO SERIES, NEVER CONFLATED - the single most important thing on the page:
//   IMPLIED   NPV guarantee / PROJECTED discounted WAR. Ex ante. The headline,
//             and what every future season's price escalates against.
//   REALIZED  paid to date / eWAR to date, off the signings ledger. Ex post.
//             A recent winter has banked little money and little WAR, so its
//             realized number is NOT comparable to an old one. Every realized
//             point carries its elapsed share and anything under 90% elapsed is
//             drawn hollow and labelled partial.
//
// Data: data/fa_meta.json -> dpw_series (the whole data/fa_dpw_series.json,
// inlined by fa_export), falling back to data/fa_dpw_series.json direct.
(function () {
  "use strict";

  const DASH = " - ";
  const ROOT_ID = "fa-dpw-view";
  const STYLE_ID = "fa-dpw-style";
  let DATA = null;
  let PRICING = null;
  let REALIZED_WAR = null;
  let IMPLIED_WAR = null;
  let loading = null;

  // The WAR basis tokens the series can carry (war_source.PROVIDERS, plus
  // "ewar_v3" before it is registered and "mixed" for a ledger on more than
  // one basis), each with its own label; only a missing or unknown basis
  // prints plain WAR. The glossary key, when one fits, rides along.
  const WAR_LABELS = {
    bwar: ["bWAR", null], ewar_v2: ["eWAR", "ewar"], ewar_v3: ["eWAR", "ewar"],
    ewar_merged: ["eWAR", "ewar"], fwar: ["fWAR", "war"], mixed: ["mixed-basis WAR", null],
  };
  function warLabel(basis) {
    const hit = WAR_LABELS[basis];
    if (!hit) return "WAR";
    return hit[1] ? `<span data-gl="${hit[1]}">${hit[0]}</span>` : hit[0];
  }
  // One sentence beside the chart, only when the two series sit on different
  // bases. It names both and says nothing about which basis is more accurate.
  function basisNote() {
    if (!IMPLIED_WAR || !REALIZED_WAR || IMPLIED_WAR === REALIZED_WAR) return "";
    return `<p class="dpw-note">The implied series is written from the free agent corpus on the
          ${warLabel(IMPLIED_WAR)} label, while the realized series reads the Archive's ledger
          on ${warLabel(REALIZED_WAR)}, so the two lines use different WAR bases.</p>`;
  }

  // ---- palette --------------------------------------------------------------
  // Two series, so two hues, and they are the only categorical assignment on
  // the page - the position/length/tier panels are SMALL MULTIPLES in one hue,
  // which is why none of them needs a six-colour scale nobody could read.
  // The hues are the site's chart tokens --viz-1 and --viz-2 (site.css, both
  // themes), the pair this view first shipped: run through the palette
  // validator against their own surface (light on #FAF5E6, dark on #1A1A1E),
  // lightness band, chroma floor, CVD separation, normal-vision floor and
  // contrast all pass. The light gold sits at 2.2:1 on paper, which is a WARN
  // that obliges visible labels - the endpoint labels and the full table below
  // are that relief.
  const CSS = `
#${ROOT_ID}{--dpw-implied:var(--viz-1);--dpw-realized:var(--viz-2);--dpw-mark:var(--text-secondary);}
#${ROOT_ID} .dpw-head{margin:0 0 .35rem;}
#${ROOT_ID} .dpw-lede{color:var(--text-secondary);max-width:64ch;margin:0 0 1rem;}
#${ROOT_ID} .dpw-panel{background:var(--bg-secondary);border:1px solid var(--border-light);
  padding:.9rem 1rem;margin:0 0 1rem;}
#${ROOT_ID} .dpw-panel > h3{margin:0 0 .15rem;font-size:1rem;}
#${ROOT_ID} .dpw-note{color:var(--text-tertiary);font-size:.8rem;margin:.1rem 0 .6rem;max-width:72ch;}
#${ROOT_ID} .dpw-legend{display:flex;flex-wrap:wrap;gap:.9rem;margin:.1rem 0 .5rem;font-size:.82rem;}
#${ROOT_ID} .dpw-legend span{display:inline-flex;align-items:center;gap:.35rem;color:var(--text-secondary);}
#${ROOT_ID} .dpw-swatch{width:14px;height:3px;display:inline-block;}
#${ROOT_ID} .dpw-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:.8rem;}
#${ROOT_ID} .dpw-cell{border:1px solid var(--border-light);padding:.5rem .6rem;}
#${ROOT_ID} .dpw-cell h4{margin:0;font-size:.85rem;display:flex;justify-content:space-between;gap:.5rem;}
#${ROOT_ID} .dpw-cell h4 em{font-style:normal;color:var(--text-secondary);font-weight:400;}
#${ROOT_ID} .dpw-cell .dpw-n{color:var(--text-tertiary);font-size:.74rem;}
#${ROOT_ID} .dpw-scroll{overflow-x:auto;}
#${ROOT_ID} table{width:100%;border-collapse:collapse;font-size:.85rem;min-width:640px;}
#${ROOT_ID} th,#${ROOT_ID} td{padding:.35rem .5rem;border-bottom:1px solid var(--border-light);
  text-align:right;white-space:nowrap;}
#${ROOT_ID} th:first-child,#${ROOT_ID} td:first-child{text-align:left;}
#${ROOT_ID} .dpw-partial{color:var(--text-tertiary);}
#${ROOT_ID}:has(> .px-state.is-loading){min-height:100vh;}
#${ROOT_ID} .dpw-how{margin:-.4rem 0 1rem;max-width:72ch;}
#${ROOT_ID} .dpw-how > summary{cursor:pointer;font-size:.8rem;color:var(--text-secondary);}
`;

  function ensureStyle() {
    if (document.getElementById(STYLE_ID)) return;
    const el = document.createElement("style");
    el.id = STYLE_ID;
    el.textContent = CSS;
    document.head.appendChild(el);
  }

  // ---- formatting -----------------------------------------------------------
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
  // A winter's total spend runs to billions and "$4095M" is a number nobody
  // reads; $/WAR never leaves the millions. One formatter, two magnitudes.
  function money(usd) {
    const n = Number(usd);
    if (!Number.isFinite(n)) return DASH;
    if (Math.abs(n) >= 1e9) return "$" + (n / 1e9).toFixed(2) + "B";
    const m = n / 1e6;
    return "$" + (Math.abs(m) >= 100 ? m.toFixed(0) : m.toFixed(1)) + "M";
  }
  function pct(x) {
    return Number.isFinite(Number(x)) ? (Number(x) * 100).toFixed(0) + "%" : DASH;
  }
  // 2027 is the 2026-27 winter. Every label on this page uses that form,
  // because "the 2027 market" means nothing to a reader who watched it happen.
  function winter(y) { return `${Number(y) - 1}-${String(y).slice(2)}`; }

  // ---- charts ---------------------------------------------------------------
  // The line chart and the small multiples are the shared hub helpers
  // (EEPHUS_HUB.lineChart and spark, assets/eephus-hub.js), which keep this
  // view's idiom: inline SVG, var() tokens only, endpoint value labels,
  // first/last ticks and a hit circle with a <title> per point. The hub snaps
  // the value axis to round 1-2-5 ticks. The "Every winter" table below prints
  // every charted number, so the hub's own numbers table is not repeated here.
  function hub() { return (typeof window !== "undefined" && window.EEPHUS_HUB) || {}; }
  function lineChart(seriesList, opts) {
    const H = hub();
    if (!H.lineChart) return "";
    const o = opts || {};
    return H.lineChart(seriesList, {
      xs: o.xs, width: o.w || 620, height: o.h || 210, pl: o.pl, floor: 0, table: false,
      fmt: money, tickFmt: v => money(v).replace(".0M", "M"), xfmt: winter,
      tip: (s, p) => `${s.label} ${winter(p.y)}: ${money(p.v)}/WAR${p.hint ? " " + p.hint : ""}`,
      aria: o.aria || "dollars per WAR by winter",
    });
  }

  // One small multiple: a single series, one hue, a SHARED scale passed in so
  // the panels are comparable to each other. No legend - the heading names it.
  function sparkPanel(title, pts, lo, hi, xs, pooled, n) {
    const H = hub();
    const svg = pts.length >= 2 && H.spark
      ? H.spark(pts, { xs, lo, hi, width: 190, height: 54, color: "var(--dpw-implied)",
          style: "display:block;width:100%;height:auto;margin:.3rem 0 0;",
          tip: p => `${winter(p.y)}: ${money(p.v)}/WAR (${p.n} deals)`,
          aria: `${title} dollars per WAR by winter` })
      : `<div class="dpw-n">too few deals per winter to plot</div>`;
    return `<div class="dpw-cell"><h4>${esc(title)}<em>${pooled == null ? DASH : money(pooled)}</em></h4>
      <div class="dpw-n">${n} deals, all winters${pooled == null ? " (too thin to price)" : ""}</div>${svg}</div>`;
  }

  // Pooled slices read as a ranked bar, not a line: they are one number per
  // bucket, and the comparison is between buckets rather than over time.
  function barRows(groups, cells) {
    const vals = groups.map(g => (cells[g] || {}).dpw).filter(v => Number.isFinite(v));
    if (!vals.length) return "";
    const hi = Math.max(...vals);
    return `<div class="dpw-scroll"><table><thead><tr><th>Bucket</th><th>Deals</th>
      <th>Spend</th><th>$/WAR</th><th style="width:40%"></th></tr></thead><tbody>` +
      groups.map(g => {
        const c = cells[g] || {};
        const w = Number.isFinite(c.dpw) ? (c.dpw / hi) * 100 : 0;
        return `<tr><td>${esc(g)}</td><td>${c.n == null ? DASH : c.n}</td>
          <td>${money(c.spend)}</td><td>${c.dpw == null ? DASH : money(c.dpw)}</td>
          <td><span style="display:block;height:9px;width:${w.toFixed(1)}%;
            background:var(--dpw-implied);" title="${esc(g)}: ${c.dpw == null ? "not priced" : money(c.dpw) + "/WAR"}"></span></td></tr>`;
      }).join("") + `</tbody></table></div>`;
  }

  // ---- view -----------------------------------------------------------------
  // M04-08: the class board's own pricing basis (fa_meta.dpw_pricing). Since
  // VAL_1 (2026-09-25) the board, /projections/ and prospect surplus all read
  // the one written series charted above, so the note says so; the older
  // two-series sentence only prints if an artifact still shows a gap.
  function pricingNote(P, head) {
    if (!P || !P.usd_per_war_by_winter || P.winter_dpw_usd == null) return "";
    const s = P.usd_per_war_by_winter;
    const cy = Number(P.class_year);
    const anchor = Object.keys(s).filter(y => Number(y) < cy).sort().pop();
    if (!anchor) return "";
    const carry = P.method === "flat5"
      ? `carried forward at ${(Number(P.escalator) * 100).toFixed(1)}%/yr`
      : `forecast by ${esc(String(P.method || "?"))}`;
    const same = Object.keys(s).every(y => Number(s[y]) === Number(head[y]));
    const projSame = P.projections_dpw_usd != null && Number(P.projections_first_season) === cy
      && Math.round(Number(P.projections_dpw_usd)) === Math.round(Number(P.winter_dpw_usd));
    if (same) {
      return `<p class="dpw-note">The class board prices on this series: ${winter(anchor)} at
        ${money(s[anchor])}, ${carry} to ${money(P.winter_dpw_usd)} for ${winter(cy)}.${projSame
        ? " /projections/ prices veteran seasons and prospect surplus prices every prospect season at that same level."
        : ""}</p>`;
    }
    const proj = P.projections_dpw_usd != null && Number(P.projections_first_season) === cy
      ? ` /projections/ prices veteran seasons at ${money(P.projections_dpw_usd)} for the same winter.`
      : "";
    return `<p class="dpw-note">The class board's series differs from the series charted above:
      ${winter(anchor)} reads ${money(s[anchor])} there against ${money(head[anchor])} here, ${carry} to
      ${money(P.winter_dpw_usd)} for ${winter(cy)}.${proj} The "Board pricing" column
      below is the board's series.</p>`;
  }

  function render(root) {
    const bd = (DATA && DATA.breakdown) || null;
    const head = (DATA && DATA.usd_per_war_by_winter) || {};
    const pser0 = (PRICING && PRICING.usd_per_war_by_winter) || null;
    // VAL_1: the "Board pricing" column only prints while the board's series
    // differs from the one written series; identical columns say nothing.
    const pser = pser0 && !Object.keys(pser0).every(y => Number(pser0[y]) === Number(head[y]))
      ? pser0 : null;
    const xs = Object.keys(head).sort();
    if (!xs.length) {
      root.innerHTML = `<div class="state-message">$/WAR series not built yet on this deploy; the nightly build writes it.
        <a href="#view=board">Back to the board</a>.</div>`;
      return;
    }
    const implied = { label: "Implied (ex ante)", color: "var(--dpw-implied)",
                      pts: xs.map(y => ({ y, v: Number(head[y]) })).filter(p => Number.isFinite(p.v)) };
    const realized = bd && bd.realized ? {
      label: "Realized (ex post)", color: "var(--dpw-realized)", dash: "5 3",
      pts: Object.keys(bd.realized).sort().map(y => {
        const r = bd.realized[y];
        return Number.isFinite(r.dpw)
          ? { y, v: r.dpw, partial: (r.elapsed || 0) < 0.9,
              hint: `(${r.n} deals, ${pct(r.elapsed)} of the terms elapsed)` }
          : null;
      }).filter(Boolean),
    } : null;
    const series = realized && realized.pts.length >= 2 ? [implied, realized] : [implied];
    const legend = series.map(s =>
      `<span><i class="dpw-swatch" style="background:${s.color}"></i>${esc(s.label)}</span>`).join("")
      + (realized ? `<span><i class="dpw-swatch" style="background:var(--bg-secondary);
        border:1.6px solid var(--dpw-realized);height:8px;width:8px;border-radius:50%"></i>under 90% elapsed</span>` : "");

    // small multiples, one shared scale across every panel
    let panels = "";
    if (bd) {
      const groups = bd.groups.pos;
      const flat = [];
      groups.forEach(g => xs.forEach(y => {
        const c = ((bd.by_winter[y] || {}).pos || {})[g];
        if (c && Number.isFinite(c.dpw)) flat.push(c.dpw);
      }));
      const lo = flat.length ? Math.min(...flat) * 0.95 : 0;
      const hi = flat.length ? Math.max(...flat) * 1.05 : 1;
      panels = groups.map(g => {
        const pts = xs.map(y => {
          const c = ((bd.by_winter[y] || {}).pos || {})[g];
          return c && Number.isFinite(c.dpw) ? { y, v: c.dpw, n: c.n } : null;
        }).filter(Boolean);
        const p = bd.pooled.pos[g] || {};
        return sparkPanel(g, pts, lo, hi, xs, p.dpw, p.n || 0);
      }).join("");
    }

    const rows = xs.map(y => {
      const w = (bd && bd.by_winter[y]) || {};
      const r = (bd && bd.realized && bd.realized[y]) || {};
      const partial = Number.isFinite(r.elapsed) && r.elapsed < 0.9;
      return `<tr><td>${winter(y)}</td><td>${w.n == null ? DASH : w.n}</td>
        <td>${money(w.spend)}</td><td>${w.qo_share == null ? DASH : pct(w.qo_share)}</td>
        <td>${money(head[y])}</td>
        ${pser ? `<td>${money(pser[y])}</td>` : ""}
        <td class="${partial ? "dpw-partial" : ""}">${r.dpw == null ? DASH : money(r.dpw)}</td>
        <td class="${partial ? "dpw-partial" : ""}">${r.elapsed == null ? DASH : pct(r.elapsed)}</td></tr>`;
    }).join("");

    const thin = bd ? bd.thresholds : { min_deals: 0, min_war: 0 };
    root.innerHTML = `
      <p><a href="#view=board">&larr; Class Board</a></p>
      <h2 class="dpw-head">FA $/WAR by winter</h2>
      <p class="dpw-lede">Implied <span data-gl="winter_dpw">$/WAR</span>: each winter's
        <span data-gl="deferral_npv">deferral-adjusted</span> guarantees over the discounted
        WAR its signings were projected to deliver.</p>
      <details class="dpw-how"><summary>How this works</summary>
        <p class="dpw-note">One $/WAR series, rewritten nightly before pricing; the class board, /projections/,
          prospect surplus, the Archive and the Club Ledger read it. Method
          ${esc((DATA && DATA.method) || "fa_signings_implied_v1")}, model
          ${esc((DATA && DATA.model_version) || "?")}; thin winters are dropped from the implied series.</p>
        ${pricingNote(PRICING, head)}
      </details>

      <div class="dpw-panel">
        <h3>Implied vs realized</h3>
        <p class="dpw-note">Realized: money paid over ${warLabel(REALIZED_WAR)} banked
          to date${REALIZED_WAR === "bwar" ? " (ledger built before the eWAR label, not rebuilt)" : ""}. Unfinished
          recent terms are not comparable to old ones; hollow points are under 90% elapsed.</p>
        ${basisNote()}
        <div class="dpw-legend">${legend}</div>
        ${lineChart(series, { xs, aria: "Implied and realized dollars per WAR by winter" })}
      </div>

      ${panels ? `<div class="dpw-panel"><h3>By position group</h3>
        <p class="dpw-note">Shared scale. Heading figure: the group pooled over all winters.
          Cells under ${thin.min_deals} deals or ${thin.min_war} projected WAR are unpriced.</p>
        <div class="dpw-grid">${panels}</div></div>` : ""}

      ${bd ? `<div class="dpw-panel"><h3>By contract length</h3>
        <p class="dpw-note">Pooled over all winters.</p>
        ${barRows(bd.groups.len, bd.pooled.len)}</div>

      <div class="dpw-panel"><h3>By guarantee tier</h3>
        <p class="dpw-note">Pooled over all winters, binned on deferral-adjusted guarantee.</p>
        ${barRows(bd.groups.tier, bd.pooled.tier)}</div>` : ""}

      <div class="dpw-panel"><h3>Every winter</h3>
        <p class="dpw-note">Spend: deferral-adjusted present value of MLB deals with enough
          history to project. QO: share of those deals that carried a
          <span data-gl="qualifying_offer">qualifying offer</span>.</p>
        <div class="dpw-scroll"><table>
          <thead><tr><th>Winter</th><th>Deals</th><th>Spend</th><th>QO</th>
            <th>Implied $/WAR</th>${pser ? "<th>Board pricing</th>" : ""}<th>Realized $/WAR</th><th>Elapsed</th></tr></thead>
          <tbody>${rows}</tbody></table></div>
      </div>`;
    // aria wiring for the [data-gl] spans; the tooltip itself is delegated.
    try { if (window.EEPHUS_GL && window.EEPHUS_GL.wire) window.EEPHUS_GL.wire(root); }
    catch (e) { /* the glossary is enrichment */ }
  }

  // ---- mount ----------------------------------------------------------------
  function isActive() {
    return new URLSearchParams(location.hash.slice(1)).get("view") === "dpw";
  }

  async function ensureData() {
    if (DATA) return DATA;
    if (loading) return loading;
    loading = (async () => {
      // fa_meta inlines the whole series file; the direct file is the fallback
      // for a build where that inline has not run yet.
      //
      // ROOT-ABSOLUTE, and that is the whole bug this view shipped with. The
      // document is served at /fa/, so a relative "data/fa_meta.json" resolved
      // to /fa/data/fa_meta.json and 404'd on BOTH candidates; the loop fell
      // through, ensureData() returned null and the view rendered nothing but
      // "The $/WAR series failed to load." It had never worked in production.
      // The house pattern is assets/fa.js's load(): `/data/${name}.json`.
      for (const url of ["/data/fa_meta.json", "/data/fa_dpw_series.json"]) {
        try {
          const r = await fetch(url, { cache: "no-store" });
          if (!r.ok) continue;
          const j = await r.json();
          const s = j.dpw_series || j;
          if (s && s.usd_per_war_by_winter) {
            DATA = s; PRICING = j.dpw_pricing || null;
            REALIZED_WAR = j.archive_war_basis || null;
            IMPLIED_WAR = j.war_provider || null;
            return DATA;
          }
        } catch (e) { /* try the next source */ }
      }
      return null;
    })();
    return loading;
  }

  function root() {
    let el = document.getElementById(ROOT_ID);
    if (el) return el;
    const rows = document.getElementById("fa-rows");
    if (!rows || !rows.parentNode) return null;
    ensureStyle();
    el = document.createElement("section");
    el.id = ROOT_ID;
    el.hidden = true;
    rows.parentNode.insertBefore(el, rows);
    return el;
  }

  async function sync() {
    const el = root();
    if (!el) return;
    const rows = document.getElementById("fa-rows");
    if (!isActive()) {
      // Leave the board exactly as it was found. fa.js keeps rendering into
      // #fa-rows the whole time this view is up; it just cannot be seen.
      el.hidden = true;
      if (rows) rows.style.removeProperty("display");
      return;
    }
    if (rows) rows.style.display = "none";
    el.hidden = false;
    if (!DATA) {
      el.innerHTML = pxState("loading", "Loading the $/WAR series.");
      await ensureData();
      if (!isActive()) return;
    }
    if (!DATA) {
      el.innerHTML = pxState("failed", `The $/WAR series
        did not load. <a href="#view=board">Back to the board</a>.`);
      return;
    }
    render(el);
  }

  window.addEventListener("hashchange", sync);
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => sync());
  } else {
    sync();
  }
  // fa.js builds #fa-rows asynchronously after its first fetch, so a deep link
  // straight to #view=dpw can land before the anchor exists. One retry pass
  // covers that without polling forever.
  setTimeout(sync, 400);
  setTimeout(sync, 1500);
})();
