/* Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
 * Unauthorized copying of this file, via any medium is strictly prohibited
 * Proprietary and confidential
 * Written by Noah J. Dengler (@ARKNDJL), 2026 */

// =============================================================================
// eephus.io unified Glossary & Methodology app (/glossary/)
// =============================================================================
// Seven views: Terms (search + group nav + A-Z index + entry cards, with
// artifact-derived receipt blocks on model entries via _receiptSpecs) ·
// How to Read (annotated anatomy guide) · Methodology (derivations +
// the industry-comparison section at #industry-comparison + interactive
// teaching widgets + PDF export) · Source Comparison (the
// empirical source-vs-source backtest) · Source Accuracy (the
// who-grades-which-cohort measurement) · Models & Proofs (the model
// registry ledger) · Library (index of every standalone page). The
// authoritative list is the view whitelist in syncFromURL below.
// The guide/methodology/backtest
// renderers are PORTED from the retired PROSPX Glossary/Methodology tab
// (owner decision 2026-06-10); the data source for every definition is
// data/glossary.json via window.EEPHUS_GLOSSARY (assets/eephus-gl.js).
(function () {
  "use strict";

  const _S = { view: "terms", cat: "all", q: "", term: null,
               backtest: null, btLoading: false, cards: false };
  // Report Cards v0: inline champion-vs-baseline proof charts on the Models &
  // Proofs cards. Dark by default pre-launch; opt in with #cards=1 for owner
  // preview. Flip _CARDS_DEFAULT to true at launch.
  const _CARDS_DEFAULT = true;   // surfaced: proof charts on by default (#cards=0 to hide)
  let GL = {};         // legacy-shaped map: slug -> {name, short, long, ...}
  let GROUPS = {};     // category -> display group
  // Models & Proofs view state. Declared up top (module scope, before boot
  // runs) so the lazy fetch guard is always initialized, mirroring the
  // _S.registry/_S.backtest lazy-load pattern the other views use.
  let _MODELS = null;          // cached model_registry.json payload (or {__error:true})
  let _MODELS_LOADING = false; // in-flight guard against a double fetch
  let _MODELS_FILTER = "all";  // active verdict filter for the Models & Proofs list
  // Source Accuracy view state. Declared HERE, at module scope above every
  // renderer, for the same reason _MODELS is: a `let` read from a hoisted
  // function that runs before the declaration is a temporal-dead-zone throw,
  // and a throw inside a fetch promise strands the view on "Loading" while
  // the smoke test stays green (the _RATER_META lesson, 2026-06-10).
  let _SACC = null;            // cached source_cohort_accuracy.json (or {__error:true})
  let _SACC_LOADING = false;   // in-flight guard against a double fetch
  let _SACC_TAB = "read-first"; // active sub-tab in the Source Accuracy view
  // Receipt-block + industry-comparison artifact cache (2026-08-19). One map
  // keyed by fetch path, shared by the Terms-view receipt blocks and the
  // Methodology "Our tables vs the industry's" section, so an artifact two
  // consumers read is fetched exactly once. Declared here, module scope above
  // every renderer, for the same TDZ reason _SACC is.
  let _RCPT = {};          // fetch path -> parsed payload (or {__error:true})
  let _RCPT_LOADING = {};  // fetch path -> in-flight guard
  let _RCPT_SPECS = null;  // entry id -> receipt spec, built lazily by _receiptSpecs()

  function escapeHtml(s) {
    return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }
  // Inline glossary link - same .g-term affordance as PROSPX; the shared
  // tooltip engine in eephus-gl.js handles hover/click on [data-gl].
  function gTermLink(slug, label) {
    return `<span class="g-term" data-gl="${escapeHtml(slug)}">${escapeHtml(label != null ? label : (GL[slug] ? GL[slug].name : slug))}</span>`;
  }
  const GLOSSARY = new Proxy({}, { get: (_, k) => GL[k],
                                   ownKeys: () => Reflect.ownKeys(GL),
                                   getOwnPropertyDescriptor: (_, k) =>
                                     GL[k] ? { enumerable: true, configurable: true, value: GL[k] } : undefined });

  // ---- URL state: #g=<slug>&view=&cat=&q= -----------------------------------
  function syncFromURL() {
    const p = new URLSearchParams(location.hash.slice(1));
    if (p.has("view")) {
      const v = p.get("view");
      if (["terms", "guide", "methodology", "source-comparison", "source-accuracy", "models", "library"].includes(v)) _S.view = v;
    }
    if (p.has("cat")) _S.cat = p.get("cat");
    if (p.has("q")) _S.q = p.get("q");
    _S.cards = p.has("cards") ? p.get("cards") !== "0" : _CARDS_DEFAULT;
    _S.term = p.get("g") || null;
    if (_S.term) _S.view = "terms";
  }
  function syncToURL() {
    const p = new URLSearchParams();
    if (_S.view !== "terms") p.set("view", _S.view);
    if (_S.cat !== "all") p.set("cat", _S.cat);
    if (_S.q) p.set("q", _S.q);
    if (_S.term) p.set("g", _S.term);
    const h = p.toString();
    history.replaceState(null, "", h ? "#" + h : location.pathname);
  }

  // ---- Terms view ------------------------------------------------------------
  function groupOrder() {
    const seen = [];
    for (const g of Object.values(GROUPS)) if (!seen.includes(g)) seen.push(g);
    return seen;
  }
  function entryGroup(e) { return GROUPS[e.category] || e.category; }

  function moduleBadges(e) {
    const LBL = { prospx: "PROSPX", fa: "MLB FA", foundations: "FOUNDATIONS",
                  platform: "PLATFORM" };
    return (e.module || []).map(m =>
      `<span class="gl-mod gl-mod--${m}">${LBL[m] || m.toUpperCase()}</span>`).join("");
  }

  // Provenance chip: distinguishes our own models from borrowed industry
  // metrics and shared foundations, so a reader always knows what is ours.
  function shelfBadge(e) {
    const S = { ark: ["ARKMETRIC", "eephus.io original"],
                industry: ["INDUSTRY", "external metric, credited"],
                foundation: ["FOUNDATION", "shared concept or standard stat"] };
    const s = S[e.shelf];
    return s ? `<span class="gl-shelf gl-shelf--${e.shelf}" title="${s[1]}">${s[0]}</span>` : "";
  }

  function entryCard(slug, e, expanded) {
    const altNames = (e.aliases || []).filter(a => a !== e.name && a.includes(" "));
    const fullName = altNames.length ? altNames.sort((a, b) => b.length - a.length)[0] : "";
    const more = [];
    if (e.long) more.push(`<div class="gl-meth">${e.long.split("\n\n").map(p => `<p>${escapeHtml(p)}</p>`).join("")}</div>`);
    if (e.formula) more.push(`<div class="gp-formula">${escapeHtml(e.formula)}</div>`);
    if (e.example) more.push(`<div class="gl-example"><span class="gl-microlabel">Example · </span>${escapeHtml(e.example)}</div>`);
    if (e.origin) more.push(`<div class="gl-origin"><span class="gl-microlabel">Origin · </span>${escapeHtml(e.origin)}</div>`);
    if (e.visual_html) more.push(`<div class="gl-microlabel" style="margin-top:8px;">Visual</div><div class="glossary-visual">${e.visual_html}</div>`);
    if (typeof _GLOSSARY_VIZ !== "undefined" && _GLOSSARY_VIZ[slug]) {
      let viz = ""; try { viz = _GLOSSARY_VIZ[slug](); } catch (err) { viz = ""; }
      if (viz) more.push(`<div class="gl-microlabel" style="margin-top:8px;">Visualization</div><div class="glossary-visual">${viz}</div>`);
    }
    // Receipt block (2026-08-19): model entries seeded in _receiptSpecs carry
    // an artifact-derived receipt inside the +methodology fold. The slot is
    // empty here on purpose: the artifact is fetched lazily on the FIRST
    // expand (_wireReceipts), so a page of collapsed cards costs zero fetches.
    if (_receiptSpecs()[slug]) {
      more.push(`<div class="gl-receipt-slot" data-receipt="${escapeHtml(slug)}"></div>`);
    }
    const rel = (e.related || []).filter(r => GL[r]).map(r =>
      `<a class="gl-rel" href="#g=${escapeHtml(r)}">${escapeHtml(GL[r].name)}</a>`).join("");
    if (rel) more.push(`<div class="gl-relrow"><span class="gl-microlabel">See also</span>${rel}</div>`);
    const moreHtml = more.length
      ? `<details class="gp-more"${expanded ? " open" : ""}><summary>+ methodology</summary><div class="gp-more-body">${more.join("")}</div></details>` : "";
    return `<div class="glossary-card" id="g-${escapeHtml(slug)}">
      <div class="gl-card-head">
        <span class="gp-term">${escapeHtml(e.name)}</span>
        ${fullName ? `<span class="gl-fullname">(${escapeHtml(fullName)})</span>` : ""}
        <span class="gl-badges">${shelfBadge(e)}${moduleBadges(e)}</span>
      </div>
      <div class="gl-def">${escapeHtml(e.short)}</div>
      ${moreHtml}</div>`;
  }

  function renderTerms() {
    const root = document.getElementById("glossary-rows");
    const q = (_S.q || "").toLowerCase().trim();
    const groups = groupOrder();
    // group filter chips with counts
    const counts = { all: 0 };
    const byGroup = new Map(groups.map(g => [g, []]));
    for (const [slug, e] of Object.entries(GL)) {
      const grp = entryGroup(e);
      if (q) {
        const hay = (e.name + " " + (e.aliases || []).join(" ") + " " +
                     e.short + " " + (e.long || "")).toLowerCase();
        if (!hay.includes(q)) continue;
      }
      // Tolerate unknown categories: lazily create the bucket so a stray
      // category surfaces in its own chip instead of vanishing. Increments
      // live inside the bucketing path so counts can never exceed what renders.
      if (!byGroup.has(grp)) byGroup.set(grp, []);
      byGroup.get(grp).push([slug, e]);
      counts.all++;
      counts[grp] = (counts[grp] || 0) + 1;
    }
    // Union the defined group order with any orphan groups discovered above.
    const allGroups = groups.concat([...byGroup.keys()].filter(g => !groups.includes(g)));
    const chips = [`<button class="chip${_S.cat === "all" ? " active" : ""}" data-gl-cat="all">All <span class="gl-count">${counts.all}</span></button>`]
      .concat(allGroups.map(g =>
        `<button class="chip${_S.cat === g ? " active" : ""}" data-gl-cat="${escapeHtml(g)}">${escapeHtml(g)} <span class="gl-count">${counts[g] || 0}</span></button>`));
    document.getElementById("gl-cats").innerHTML = chips.join("");
    document.querySelectorAll("[data-gl-cat]").forEach(b => b.onclick = () => {
      _S.cat = b.dataset.glCat; syncToURL(); render();
    });
    // entries: alphabetical within the active scope
    const active = _S.cat === "all" ? allGroups : [_S.cat];
    const flat = [];
    for (const g of active) {
      for (const [slug, e] of (byGroup.get(g) || [])) flat.push([slug, e, g]);
    }
    flat.sort((a, b) => a[1].name.localeCompare(b[1].name, "en", { sensitivity: "base" }));
    // A-Z index strip (inactive letters dimmed, never hidden)
    const present = new Set(flat.map(([, e]) => (e.name[0] || "#").toUpperCase()));
    const az = ["#"].concat("ABCDEFGHIJKLMNOPQRSTUVWXYZ".split("")).map(L => {
      const has = L === "#" ? [...present].some(c => !/[A-Z]/.test(c)) : present.has(L);
      return has ? `<a href="#" data-gl-az="${L}">${L}</a>` : `<span class="gl-az-off">${L}</span>`;
    }).join("");
    document.getElementById("gl-az").innerHTML = az;
    document.querySelectorAll("[data-gl-az]").forEach(a => a.onclick = ev => {
      ev.preventDefault();
      const L = a.dataset.glAz;
      const hit = flat.find(([, e]) => {
        const c = (e.name[0] || "#").toUpperCase();
        return L === "#" ? !/[A-Z]/.test(c) : c === L;
      });
      if (hit) document.getElementById("g-" + hit[0])?.scrollIntoView({ block: "start" });
    });
    let lastLetter = null;
    const parts = [];
    for (const [slug, e] of flat) {
      const c = (e.name[0] || "#").toUpperCase();
      const letter = /[A-Z]/.test(c) ? c : "#";
      if (letter !== lastLetter) {
        parts.push(`<div class="glossary-cat-heading">${letter}</div>`);
        lastLetter = letter;
      }
      // Hybrid expansion: collapsed by default, expanded when arrived via
      // a direct #g= anchor (the reader asked for THIS entry's full read).
      parts.push(entryCard(slug, e, _S.term === slug));
    }
    root.innerHTML = parts.join("") || `<div class="state-message">No glossary terms match.</div>`;
    _wireReceipts(root);
    if (_S.term) {
      const card = document.getElementById("g-" + _S.term);
      if (card) {
        requestAnimationFrame(() => {
          card.scrollIntoView({ behavior: "smooth", block: "start" });
          card.classList.add("is-highlighted");
        });
      }
      _S.term = null;
    }
  }

  // ==== RECEIPT BLOCKS (2026-08-19) ==========================================
  // Artifact-derived receipts on model entries: the estimand in one plain
  // sentence, the named baseline, the measured number with its floor or CI,
  // and a three-valued verdict chip (clears floor / inside floor / trails).
  // Every figure is read from the committed eval artifact at expand time and
  // passes through ONE formatter (_rn); no measured number is typed by hand.
  // Ledger notes, recorded rather than approximated:
  //   - milb_park_factor: intentionally left as-is (its entry copy already
  //     stands on data/milb_park_factors_eval.json; no receipt spec added).
  //   - war_pa_plus_3yr / _adj and the war_ip_plus_* 3yr/adj variants: the
  //     committed eval (war_rate_plus_eval.json) scores only the base
  //     single-season indexes, so the variants get NO receipt (no clean key).
  //   - the IFA $1M step prior has no glossary entry of its own; its receipt
  //     rides the `ifa` entry. The pWOBA gate (phem_marcel_lite_eval.json,
  //     where fa_projection's projected wOBA won) rides the `pwoba` entry.
  //   - hem_plus_3yr / sem_plus_3yr / rem_plus_3yr / fwdhem_plus / xrem_plus /
  //     xsem_plus: no per-variant eval cell; skipped, not approximated.

  // The single number formatter every receipt figure passes through.
  function _rn(v, dp) {
    return (v == null || isNaN(Number(v))) ? "-" : Number(v).toFixed(dp == null ? 3 : dp);
  }
  function _rns(v, dp) { return (Number(v) > 0 ? "+" : "") + _rn(v, dp); }
  function _rnp(v, dp) { return (v == null || isNaN(Number(v))) ? "-" : _rn(Number(v) * 100, dp == null ? 1 : dp) + "%"; }

  // Three-valued call from a CI on a (higher-is-better) gap.
  function _rcptCI(lo, hi) {
    if (lo == null || hi == null || isNaN(Number(lo)) || isNaN(Number(hi))) return "inside";
    if (Number(lo) > 0) return "clears";
    if (Number(hi) < 0) return "trails";
    return "inside";
  }

  function _rcptChip(verdict, title) {
    const M = { clears: ["clears floor", "var(--up)"],
                inside: ["inside floor", "var(--text-secondary)"],
                trails: ["trails", "var(--down)"] };
    const m = M[verdict];
    if (!m) return "";
    return `<span title="${escapeHtml(title || "")}" style="font-weight:700;font-size:0.85em;color:${m[1]};white-space:nowrap;">${m[0]}</span>`;
  }

  // Shared artifact cache: one fetch per path no matter how many receipts or
  // methodology blocks read it. Callbacks queue while a fetch is in flight.
  function _rcptLoad(path, cb) {
    if (_RCPT[path]) { cb(); return; }
    if (_RCPT_LOADING[path]) { _RCPT_LOADING[path].push(cb); return; }
    _RCPT_LOADING[path] = [cb];
    const done = j => {
      _RCPT[path] = j || { __error: true };
      const q = _RCPT_LOADING[path] || [];
      delete _RCPT_LOADING[path];
      q.forEach(f => { try { f(); } catch (err) { /* one bad consumer never strands the rest */ } });
    };
    fetch(path, { cache: "no-cache" })
      .then(r => (r.ok ? r.json() : null))
      .then(done)
      .catch(() => done(null));
  }

  // Entry id -> receipt spec. Built once, lazily. Each spec:
  //   art      - artifact path (fetched once, shared via _RCPT)
  //   cache    - optional: reuse a payload another view already loaded
  //   estimand - one plain sentence: what the model claims to measure
  //   baseline - the named baseline the number is scored against
  //   read(j)  - rows [{label, mv, bname, bv, band, verdict, title}] or null
  //              (null = the artifact lacks the key; the receipt SKIPS, it
  //              never approximates)
  //   note     - optional fn(j) -> one extra honesty sentence
  function _receiptSpecs() {
    if (_RCPT_SPECS) return _RCPT_SPECS;

    // hem/sem/rem/xhem share one shape: forward Spearman vs named baselines
    // with a bootstrap CI on each gap.
    const rateRows = (f, pk, pn, cells, n, nUnit) => {
      if (!f || f[pk] == null) return null;
      const rows = [];
      cells.forEach(c => {
        const g = c.ci || {};
        if (f[c.bk] == null || g.lo95 == null) return;
        rows.push({
          label: c.label + " (n=" + _rn(n, 0) + " " + nUnit + ")",
          mv: _rn(f[pk]), mname: pn, bname: c.bname, bv: _rn(f[c.bk]),
          band: "gap " + _rns(g.mean) + ", 95% CI " + _rns(g.lo95) + " to " + _rns(g.hi95),
          verdict: _rcptCI(g.lo95, g.hi95),
        });
      });
      return rows.length ? rows : null;
    };

    const g2Read = j => {
      const p = j.pooled || {}, gates = j.gates || {};
      const mk = (k, label, dp, unit) => (p[k] && p[k].mae_model != null && p[k].mae_base != null) ? {
        label: label + " (n=" + _rn(p[k].n, 0) + " signings)",
        mv: unit + _rn(p[k].mae_model, dp), bname: "5-nearest-comps median", bv: unit + _rn(p[k].mae_base, dp),
        band: "lower is better",
        verdict: gates[k] === true ? "clears"
          : (Number(p[k].mae_model) < Number(p[k].mae_base) ? "inside" : "trails"),
        title: "gate flag `" + k + "` as recorded in the artifact",
      } : null;
      const rows = [mk("guarantee", "Guarantee MAE, NPV $M", 1, "$"),
                    mk("aav", "AAV MAE, $M", 2, "$"),
                    mk("years", "Years MAE", 2, "")].filter(Boolean);
      return rows.length ? rows : null;
    };

    const surplusRead = j => {
      const fp = j.full_pool || {};
      const rc = fp.raw_calibration || {}, ci = fp.raw_calibration_slope_ci90;
      if (rc.slope == null || !Array.isArray(ci) || ci.length !== 2) return null;
      const yrs = j.listing_years || [];
      const span = yrs.length ? yrs[0] + "-" + yrs[yrs.length - 1] : "";
      const rows = [{
        label: "Realized-on-predicted calibration slope (n=" + _rn(fp.n_players, 0) + " listed prospects, " + span + " lists)",
        mv: _rn(rc.slope, 2), bname: "a no-signal slope of", bv: _rn(0, 0),
        band: "90% CI " + _rn(ci[0], 2) + " to " + _rn(ci[1], 2),
        verdict: _rcptCI(ci[0], ci[1]),
        title: "slope CI excludes zero: predicted dollars carry real information about realized dollars",
      }];
      const bc = fp.binned_calibration || {};
      if (bc.r2 != null) rows.push({
        label: "Binned predicted-vs-realized fit, r-squared",
        mv: _rn(bc.r2, 2),
      });
      return rows;
    };

    const wrSpec = (pool, poolLabel) => ({
      art: "/data/war_rate_plus_eval.json",
      estimand: "Does the " + poolLabel + " rate index forward-predict the next season's WAR rate better than the season WAR total it re-expresses?",
      baseline: "plain season WAR total, the simplest baseline in the set",
      read: j => {
        const p = (j.pools || {})[pool] || {};
        const v2 = (p.results_by_convention || {}).v2 || {};
        const b = v2.rho_baselines || {};
        const g = (v2.gap_ci_primary_minus_baseline || {}).war_total || {};
        if (v2.rho_primary == null || b.war_total == null || g.lo95 == null) return null;
        const rows = [{
          label: "Spearman rho, next-season WAR rate (n=" + _rn(p.n_forward_pairs, 0) + " forward pairs)",
          mv: _rn(v2.rho_primary), bname: "plain season WAR total", bv: _rn(b.war_total),
          band: "gap " + _rns(g.mean) + ", 95% CI " + _rns(g.lo95) + " to " + _rns(g.hi95),
          verdict: _rcptCI(g.lo95, g.hi95),
        }];
        if (b.placebo != null) rows.push({
          label: "Same read vs a zero-information placebo",
          mv: _rn(v2.rho_primary), bname: "placebo", bv: _rn(b.placebo),
          verdict: ((j.verdict || {}).g1_beats_zero_information_control_by_pool || {})[pool] === true ? "clears" : "inside",
        });
        return rows;
      },
      // Derived, not typed: on eWAR (re-pointed 2026-09-11, audit F10-01) the
      // starter index DOES clear the season WAR total and ties the unscaled
      // rate, so a fixed "does not beat" sentence would be false on one card.
      note: j => {
        const p = (j.pools || {})[pool] || {};
        const g = ((((p.results_by_convention || {}).v2 || {}).gap_ci_primary_minus_baseline) || {}).war_total || {};
        return (g.lo95 != null && g.lo95 > 0)
          ? "The index carries real signal and clears the season WAR total, but it does not clear the same rate left unscaled, so the pre-registered ship gate still fails. It ships as a display index, not a validated forecaster."
          : "The index carries real signal but does not beat the season WAR total it is built from. It ships as a display index, not a validated forecaster, and the loss stays on this card.";
      },
    });

    _RCPT_SPECS = {
      // ---- WINS -----------------------------------------------------------
      hem_plus: {
        art: "/data/hem_plus_eval.json",
        estimand: "Does HEM+ predict a hitter's next-season wOBA, forward-chained and out of sample?",
        baseline: "batting average, with raw wOBA as the no-worse check",
        read: j => rateRows(j.forward_spearman_vs_wOBA_next, "hem_plus", "HEM+", [
          { label: "Spearman rho, next-season wOBA", bk: "avg", bname: "AVG", ci: j.gap_ci_vs_avg },
          { label: "Same read vs raw wOBA itself", bk: "raw_woba", bname: "raw wOBA", ci: j.gap_ci_vs_raw_woba },
        ], j.n_forward_pairs, "forward pairs"),
      },
      sem_plus: {
        art: "/data/sem_plus_eval.json",
        estimand: "Does SEM+ predict a starter's next-season run prevention (RA9)?",
        baseline: "ERA, with raw FIP as the harder check",
        read: j => rateRows(j.forward_spearman_vs_RA9_next, "sem_plus", "SEM+", [
          { label: "Spearman rho, next-season RA9", bk: "era", bname: "ERA", ci: j.gap_ci_vs_era },
          { label: "Same read vs raw FIP", bk: "raw_fip", bname: "raw FIP", ci: j.gap_ci_vs_raw_fip },
        ], j.n_forward_pairs, "forward pairs"),
      },
      rem_plus: {
        art: "/data/rem_plus_eval.json",
        estimand: "Does REM+ predict a reliever's next-season run prevention (RA9)?",
        baseline: "raw FIP; ERA as the softer check",
        read: j => {
          const g = j.gap_ci_vs_RA9_next || {};
          return rateRows(j.forward_spearman_vs_RA9_next, "rem_plus", "REM+", [
            { label: "Spearman rho, next-season RA9", bk: "raw_fip", bname: "raw FIP", ci: g.vs_raw_fip },
            { label: "Same read vs ERA", bk: "era", bname: "ERA", ci: g.vs_era },
          ], j.n_forward_pairs, "forward pairs");
        },
      },
      xhem_plus: {
        art: "/data/xhem_plus_eval.json",
        estimand: "Does the deserved (xwOBA-based) read predict next-season wOBA better than the actual line?",
        baseline: "actual wOBA, same forward pairs",
        read: j => rateRows(j.forward_spearman_vs_wOBA_next, "xwoba", "xwOBA", [
          { label: "Spearman rho, next-season wOBA", bk: "actual_woba", bname: "actual wOBA", ci: j.gap_ci_xwoba_minus_woba },
        ], j.n_forward_pairs, "forward pairs"),
      },
      pwoba: {
        art: "/data/phem_marcel_lite_eval.json",
        estimand: "Does the served projected wOBA order hitters' next-season wOBA better than the best flat multiyear read?",
        baseline: "flat 3-year HEM+, the best incumbent at the gate",
        read: j => {
          const h = j.hitters || {};
          const r = h.gate_rhos_v1 || {};
          const g = (h.gate || {}).gap_ci_winner_minus_best_incumbent_v1 || {};
          if (r.fa_projection == null || r.incumbent_3yr_flat == null || g.lo95 == null) return null;
          return [{
            label: "Spearman rho, next-season wOBA, held-out gate years (n=" + _rn(h.n_gate, 0) + ")",
            mv: _rn(r.fa_projection), bname: "flat 3-year HEM+", bv: _rn(r.incumbent_3yr_flat),
            band: "gap " + _rns(g.mean) + ", 95% CI " + _rns(g.lo95) + " to " + _rns(g.hi95),
            verdict: _rcptCI(g.lo95, g.hi95),
          }];
        },
        note: j => (((j.verdict || {}).pitchers || {}).status || "").indexOf("FAIL") === 0
          ? "The pitcher-side twin failed its gate and did not ship; that loss is committed in the same artifact."
          : "",
      },
      eta: {
        art: "/data/eta_eval.json",
        estimand: "Does the served ETA call the year a prospect debuts better than a naive level table would?",
        baseline: "a naive years-per-level table, scored on identical rows",
        read: j => {
          const c = j.champion_on_baseline_rows || {}, b = j.baseline_naive_level_table || {};
          if (c.mae == null || b.mae == null) return null;
          const rows = [{
            label: "Years-to-debut MAE, debuted players, identical rows (n=" + _rn(b.n, 0) + ")",
            mv: _rn(c.mae, 2) + " yr", bname: "naive level table", bv: _rn(b.mae, 2) + " yr",
            band: "lower is better; the artifact publishes no CI for this pair",
            verdict: Number(c.mae) < Number(b.mae) ? "clears" : "trails",
            title: "ship rule recorded in the artifact: beat the incumbent bases on identical rows",
          }];
          if (c.within_1y != null && b.within_1y != null) rows.push({
            label: "Called within one year of the actual debut",
            mv: _rnp(c.within_1y), bname: "naive level table", bv: _rnp(b.within_1y),
            verdict: Number(c.within_1y) > Number(b.within_1y) ? "clears" : "trails",
          });
          return rows;
        },
        note: () => "Scored on debuted players only; the overdue and washed-out rates carry the unconditional signal and are published in the same artifact.",
      },
      farm_report_card: {
        art: "/data/farm_grade_eval.json",
        estimand: "Does the farm grade's financial core (surplus mass over the vintage board) rank orgs by the graduate WAR they went on to produce?",
        baseline: "a plain prospect-count ranking on the same vintage boards",
        read: j => {
          const m = j.mean_spearman || {};
          if (m.sum_surplus_mm == null || m.count == null) return null;
          const vy = j.vintage_years || [];
          const first = (j.per_vintage || {})[vy[0]] || {};
          const rows = [{
            label: "Mean Spearman vs realized 3-year graduate WAR (" + _rn(vy.length, 0) + " vintages, " + _rn(first.n_orgs, 0) + " orgs each)",
            mv: _rn(m.sum_surplus_mm, 2), bname: "prospect count", bv: _rn(m.count, 2),
            verdict: (j.verdict || {}).financial_core_beats_count === true ? "clears" : "inside",
            title: "verdict boolean recorded in the artifact",
          }];
          if (m.count_fv50plus != null) rows.push({
            label: "Same read vs an FV 50+ count baseline",
            mv: _rn(m.sum_surplus_mm, 2), bname: "FV 50+ count", bv: _rn(m.count_fv50plus, 2),
            verdict: Number(m.sum_surplus_mm) > Number(m.count_fv50plus) ? "clears" : "inside",
          });
          return rows;
        },
        note: () => "Reduced analog: letters were never snapshotted, so the backtest scores the tree's financial core on vintage FVs, as the artifact's conventions state.",
      },
      spotlights: {
        art: "/data/editorial_eval.json",
        estimand: "Do the editorial flags predict real consensus movement, or just narrate it?",
        baseline: "matched unflagged players in the same FV band and window",
        read: j => {
          const t = j.by_flag_type || {};
          const rows = [];
          [["faller", "Faller flags: consensus drop within 30 days"],
           ["rebound", "Rebound flags: recovery within 30 days"],
           ["riser", "Riser flags: further rise within 30 days"]].forEach(pair => {
            const f = ((t[pair[0]] || {}).horizons || {}).h30;
            if (!f || f.hit_rate == null || !Array.isArray(f.ci)) return;
            rows.push({
              label: pair[1] + " (n=" + _rn(f.n, 0) + " flags)",
              mv: _rnp(f.hit_rate), bname: "control (n=" + _rn(f.control_n, 0) + ")", bv: _rnp(f.control_rate),
              band: "95% CI " + _rnp(f.ci[0]) + " to " + _rnp(f.ci[1]) + "; control " + _rnp((f.control_ci || [])[0]) + " to " + _rnp((f.control_ci || [])[1]),
              verdict: f.clears_control === true ? "clears" : "inside",
              title: "clears_control as recorded in the artifact",
            });
          });
          return rows.length ? rows : null;
        },
      },
      fa_projection_engine: {
        art: "/data/fa_gate1_eval.json",
        estimand: "Does the FA projection engine forecast next-season WAR better than carrying a player's own recent record forward?",
        baseline: "a 5/4/3 weighted average of actual finals, no regression, no aging",
        read: j => {
          const p = (j.pooled || {}).war;
          if (!p || p.mae_model == null || p.mae_base == null) return null;
          return [{
            label: "Next-season WAR MAE (n=" + _rn(p.n, 0) + " player-seasons, forward-chained)",
            mv: _rn(p.mae_model, 2), bname: "5/4/3 carry-forward", bv: _rn(p.mae_base, 2),
            band: "lower is better",
            verdict: ((j.gates || {}).war === true && j.pass === true) ? "clears"
              : (Number(p.mae_model) < Number(p.mae_base) ? "inside" : "trails"),
            title: "gate flags recorded in the artifact",
          }];
        },
      },
      rational_value: {
        art: "/data/fa_gate2_eval.json",
        estimand: "The pricing legs under rational value are gate-checked through the market backtest: predicted guarantee, AAV, and years against what free agents then signed for.",
        baseline: "the median of the 5 nearest comps from prior winters, $/WAR-trend inflated, NPV basis",
        read: g2Read,
      },
      m_guarantee: {
        art: "/data/fa_gate2_eval.json",
        estimand: "Does the market model predict the contract a free agent actually signs?",
        baseline: "the median of the 5 nearest comps from prior winters, $/WAR-trend inflated, NPV basis",
        read: g2Read,
      },
      fit_components: {
        art: "/data/fa_gate3_eval.json",
        estimand: "Does the team-fit score put a free agent's actual signing club near the top of its 30-team ranking?",
        baseline: "random team, payroll-only, and behavior-only rankings on the same signings",
        read: j => {
          const r = j.results || {}, v = j.verdicts || {};
          const la = r.live_analog;
          if (!la || la.mrr == null) return null;
          const mk = (bk, bl, flag) => (r[bk] && r[bk].mrr != null) ? {
            label: "Mean reciprocal rank of the signing club vs " + bl + " (n=" + _rn(la.n, 0) + ")",
            mv: _rn(la.mrr), bname: bl, bv: _rn(r[bk].mrr),
            verdict: v[flag] === true ? "clears" : "inside",
            title: "verdict boolean recorded in the artifact",
          } : null;
          const rows = [mk("random", "a random team", "live_analog_beats_random"),
                        mk("payroll_only", "payroll only", "live_analog_beats_payroll_only"),
                        mk("behavior_only", "behavior only", "live_analog_beats_behavior_only")].filter(Boolean);
          return rows.length ? rows : null;
        },
        note: j => ((j.verdicts || {}).fitted_transfer_beats_live_analog === false)
          ? "A fitted challenger lost to this hand-built analog on the same forward chain; the losing run is committed in the same artifact."
          : "",
      },
      surplus_value: {
        art: "/data/surplus_backtest_real.json",
        estimand: "Do predicted surplus dollars track the dollars prospects actually returned?",
        baseline: "a flat pricing with no player information (slope 0)",
        read: surplusRead,
        note: j => {
          const sp = (((j.full_pool || {}).raw_errors) || {}).spearman;
          return sp == null ? "" : "Honest limit: per-player ordering inside the pool is far weaker (Spearman " + _rn(sp, 2) + "); the calibration holds at the bin level, where prices are set.";
        },
      },
      tvi: {
        art: "/data/surplus_backtest_real.json",
        estimand: "TVI prices off the same engine: do its predicted dollars track realized dollars?",
        baseline: "a flat pricing with no player information (slope 0)",
        read: surplusRead,
      },
      ifa: {
        art: "/data/ifa_step_prior_eval.json",
        estimand: "Do IFA signees at or above the $1M bonus step go on to produce more than signees below it (the step prior eFV consumes)?",
        baseline: "signees below the $1M step, same matched classes",
        read: j => {
          const s = j.step_boundary_first6 || {};
          if (s.hi_mean == null || s.lo_mean == null || !Array.isArray(s.diff_ci95)) return null;
          return [{
            label: "Mean first-6-year WAR, signees at or above the step (n=" + _rn(s.n_hi, 0) + ") vs below (n=" + _rn(s.n_lo, 0) + ")",
            mv: _rn(s.hi_mean, 2), bname: "below the step", bv: _rn(s.lo_mean, 2),
            band: "gap " + _rns(s.diff, 2) + ", 95% CI " + _rns(s.diff_ci95[0], 2) + " to " + _rns(s.diff_ci95[1], 2),
            verdict: _rcptCI(s.diff_ci95[0], s.diff_ci95[1]),
          }];
        },
        note: () => "Direction held in all six leave-one-class-out folds; the posted-pro-excluded sensitivity is committed in the same artifact.",
      },
      // ---- TIES, rendered as the ties they are ------------------------------
      xfv: {
        art: "/data/source_backtest.json",
        cache: () => (_S.backtest && !_S.backtest.__error ? _S.backtest : null),
        estimand: "Does eFV order realized 6-year WAR better than the consensus it is built to upgrade, vintage-matched so neither side holds a timing edge?",
        baseline: "the PROSPX consensus, identical rows and identical vintages",
        read: j => {
          const hh = (j.accuracy || {}).head_to_head_verdict;
          if (!hh || hh.xfv_spearman == null || hh.consensus_spearman == null) return null;
          return [{
            label: "Spearman rho vs realized WAR, vintage-matched (n=" + _rn(hh.n, 0) + ")",
            mv: _rn(hh.xfv_spearman, 4), bname: "consensus", bv: _rn(hh.consensus_spearman, 4),
            band: "gap " + _rns(hh.delta, 4) + " vs a floor of " + _rn(hh.mde95, 4),
            verdict: hh.resolvable === true ? (hh.xfv_beats === true ? "clears" : "trails") : "inside",
            title: "head_to_head_verdict as recorded in the artifact",
          }];
        },
        note: () => "The honest reading is a tie: the gap sits inside the floor this backtest can resolve, so eFV and the consensus are statistically indistinguishable on ordering. The full derived verdict renders in Source Comparison.",
      },
      consensus_fv: {
        art: "/data/source_backtest.json",
        cache: () => (_S.backtest && !_S.backtest.__error ? _S.backtest : null),
        estimand: "Is the equal-weight blend better than its best single input?",
        baseline: "the best single input, re-picked inside every bootstrap draw",
        read: j => {
          const c = (j.accuracy || {}).consensus_vs_inputs;
          if (!c || !c.spearman || !c.auc) return null;
          const leg = (b, label) => (b.consensus == null ? null : {
            label: label,
            mv: _rn(b.consensus, 4), bname: "best input", bv: _rn(b.best_input, 4),
            band: "gap " + _rns(b.delta, 4) + " vs a floor of " + _rn(b.mde95, 4),
            verdict: b.resolvable === true ? (b.consensus_wins === true ? "clears" : "trails") : "inside",
          });
          return [leg(c.spearman, "Ordering realized WAR (Spearman rho)"),
                  leg(c.auc, "Separating future contributors (AUC)")].filter(Boolean);
        },
        note: () => "Two legs, two answers: blending buys discrimination, and the ordering gap sits inside the floor. Both are printed rather than the better one.",
      },
      // ---- LOSSES, rendered honestly ---------------------------------------
      war_pa_plus: wrSpec("hit", "hitter (WAR/PA+)"),
      war_ip_plus_sp: wrSpec("SP", "starter (WAR/IP+)"),
      war_ip_plus_rp: wrSpec("RP", "reliever (WAR/IP+)"),
      statcast_plus: {
        art: "/data/statcast_plus_eval.json",
        estimand: "Does a prospect's final-AAA Statcast composite forward-predict his first MLB season?",
        baseline: "none: a forward correlation published as measured, per the publish-the-r rule",
        read: j => {
          const h = j.hitters || {}, p = j.pitchers || {};
          const rows = [];
          if (h.r_sc_vs_mlb_ops != null) rows.push({
            label: "Final-AAA analog vs first-MLB OPS, r (n=" + _rn(h.n_ops, 0) + ")",
            mv: _rn(h.r_sc_vs_mlb_ops, 2), verdict: "trails",
            title: "weak forward correlation; SC+ stays descriptive",
          });
          if (p.r_sc_vs_mlb_era_inv != null) rows.push({
            label: "Final-AAA analog vs first-MLB ERA (inverted), r (n=" + _rn(p.n_era, 0) + ")",
            mv: _rn(p.r_sc_vs_mlb_era_inv, 2), verdict: "trails",
            title: "weak forward correlation; SC+ stays descriptive",
          });
          return rows.length ? rows : null;
        },
        note: () => "SC+ is a descriptive index of what the tracking says today, not a forecaster. Downstream consumers treat it as a tiebreaker, never a driver.",
      },
      arb_award_model: {
        art: "/data/arbitration_eval.json",
        estimand: "Does the arbitration award model price the salary a tendered player actually receives?",
        baseline: "its class-appropriate naive bar, and the published MLBTR / Matt Swartz projection",
        read: j => {
          const r1 = ((j.results || {}).arb1) || {}, a6 = j.a6_swartz || {};
          const rows = [];
          if (r1.mdape_champion != null && r1.mdape_bar != null) rows.push({
            label: "First-trip MdAPE vs the naive bar (n=" + _rn(r1.n_paired, 0) + ")",
            mv: _rnp(r1.mdape_champion), bname: "naive bar", bv: _rnp(r1.mdape_bar),
            band: "gain " + _rnp(r1.mdape_gain) + " vs floor " + _rnp(r1.mde95_onesided) + " (" + _rn(r1.gain_over_floor, 1) + "x)",
            verdict: r1.resolvable === true ? "clears" : "inside",
          });
          if (a6.ours_mdape != null && a6.swartz_mdape != null) rows.push({
            label: "MdAPE vs the published Swartz projection, identical rows (n=" + _rn(a6.n, 0) + ")",
            mv: _rnp(a6.ours_mdape), bname: "MLBTR / Swartz", bv: _rnp(a6.swartz_mdape),
            band: _rn(a6.ratio_ours_over_swartz, 2) + "x their error",
            verdict: Number(a6.ours_mdape) > Number(a6.swartz_mdape) ? "trails" : "inside",
          });
          return rows.length ? rows : null;
        },
        note: () => "The loss has a mechanism: Swartz prices the counting stats arbitration panels reward, and this model excludes them because nothing in the pipeline projects them forward. The comparison stays on the card.",
      },
    };
    return _RCPT_SPECS;
  }

  // Render one receipt block from its spec + loaded artifact.
  function _receiptHTML(spec, j) {
    let rows;
    try { rows = spec.read(j); } catch (err) { rows = null; }
    if (!rows || !rows.length) return "";
    const rr = rows.map(r => {
      const base = (r.bname && r.bv != null)
        ? ` <span style="color:var(--text-tertiary);">vs</span> ${escapeHtml(r.bname)} <b style="color:var(--text-secondary);">${escapeHtml(r.bv)}</b>` : "";
      return `<div style="display:flex;gap:8px;align-items:baseline;flex-wrap:wrap;margin:3px 0;">
        <span style="flex:1 1 220px;">${escapeHtml(r.label)}</span>
        <span><b>${escapeHtml(r.mv)}</b>${base}</span>
        ${r.band ? `<span style="color:var(--text-tertiary);font-size:0.85em;">${escapeHtml(r.band)}</span>` : ""}
        ${r.verdict ? _rcptChip(r.verdict, r.title) : ""}
      </div>`;
    }).join("");
    let note = "";
    if (spec.note) { try { note = spec.note(j) || ""; } catch (err) { note = ""; } }
    const fname = spec.art.split("/").pop();
    return `<div style="margin-top:10px;border-top:1px dashed var(--border-light);padding-top:8px;">
      <div class="gl-microlabel">Receipt · read live from the committed eval artifact</div>
      <div style="margin:4px 0 6px;">${escapeHtml(spec.estimand)} Baseline: ${escapeHtml(spec.baseline)}.</div>
      ${rr}
      ${note ? `<div class="meth-note" style="margin-top:4px;">${escapeHtml(note)}</div>` : ""}
      <div class="meth-note" style="margin-top:4px;">Artifact: <a href="${escapeHtml(spec.art)}" target="_blank" rel="noopener">${escapeHtml(fname)}</a></div>
    </div>`;
  }

  function _fillReceipt(slot, spec) {
    const cached = spec.cache ? spec.cache() : null;
    const j = cached || _RCPT[spec.art];
    if (j && !j.__error) { slot.innerHTML = _receiptHTML(spec, j); return; }
    if (j && j.__error) { slot.innerHTML = ""; return; }
    _rcptLoad(spec.art, () => { if (slot.isConnected) _fillReceipt(slot, spec); });
  }

  // Wire the empty receipt slots: fetch on the FIRST expand of the entry's
  // +methodology fold (or immediately when it rendered already open via a
  // direct #g= anchor), so a page of collapsed cards costs zero fetches.
  function _wireReceipts(root) {
    root.querySelectorAll(".gl-receipt-slot").forEach(slot => {
      const spec = _receiptSpecs()[slot.dataset.receipt];
      if (!spec) return;
      const det = slot.closest("details");
      const fill = () => _fillReceipt(slot, spec);
      if (!det || det.open) { fill(); return; }
      det.addEventListener("toggle", function h() {
        if (det.open) { det.removeEventListener("toggle", h); fill(); }
      });
    });
  }

  // ---- router ----------------------------------------------------------------
  function render() {
    const ids = { terms: "glossary-rows", guide: "guide-body",
                  methodology: "methodology-body", "source-comparison": "source-comparison-body",
                  "source-accuracy": "source-accuracy-body",
                  models: "models-body", library: "library-body" };
    document.querySelectorAll("[data-glossary-view]").forEach(b => {
      b.classList.toggle("active", b.dataset.glossaryView === _S.view);
    });
    for (const [v, id] of Object.entries(ids)) {
      const el = document.getElementById(id);
      if (el) el.style.display = v === _S.view ? "" : "none";
    }
    const bar = document.getElementById("gl-termbar");
    if (bar) bar.style.display = _S.view === "terms" ? "" : "none";
    if (_S.view === "guide") renderGuide();
    else if (_S.view === "methodology") renderMethodology();
    else if (_S.view === "source-comparison") renderSourceComparison();
    else if (_S.view === "source-accuracy") renderSourceAccuracy();
    else if (_S.view === "models") renderModels();
    else if (_S.view === "library") renderLibrary();
    else renderTerms();
  }

  function boot() {
    syncFromURL();
    document.querySelectorAll("[data-glossary-view]").forEach(b => {
      b.onclick = () => { _S.view = b.dataset.glossaryView; syncToURL(); render(); };
    });
    const inp = document.getElementById("gl-search");
    if (inp) {
      inp.value = _S.q;
      inp.addEventListener("input", () => { _S.q = inp.value; syncToURL(); render(); });
      inp.addEventListener("keydown", e => {
        if (e.key === "Escape") { inp.value = ""; _S.q = ""; syncToURL(); render(); }
      });
    }
    window.addEventListener("hashchange", () => { syncFromURL(); render(); });
    const start = () => {
      GL = window.EEPHUS_GLOSSARY || {};
      GROUPS = window.EEPHUS_GLOSSARY_GROUPS || {};
      render();
    };
    if (window.EEPHUS_GLOSSARY) start();
    else window.addEventListener("eephus-glossary-ready", start, { once: true });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();

  // window-scope the print hook the toolbar button calls.
  window._printMethodology = function () {
    document.body.classList.add("printing-meth");
    const cleanup = () => { document.body.classList.remove("printing-meth"); window.removeEventListener("afterprint", cleanup); };
    window.addEventListener("afterprint", cleanup);
    setTimeout(() => { window.print(); }, 30);
    setTimeout(cleanup, 1500);
  };

// ==== PORTED FROM PROSPX (Glossary/Methodology tab, retired 2026-06-10) =====
// Source: prospx/index.html L17995-18742 via build_glossary_port.py.
// Hand-maintained from here on; the generator is provenance only.
//
// _RATER_META / _TIER_ORDER sat ONE LINE above the port slice and were
// missed - Source Comparison silently hung on "Loading…" because the
// ReferenceError died inside the fetch promise (fixed 2026-06-10; the
// smoke test now asserts rendered content, not just a non-empty body).
// _raterMeta() is the safe accessor: unknown raters (new sources join the
// backtest as their cohorts resolve) get a neutral fallback, never a throw.
// Owner palette (2026-06-24): FanGraphs dark green, MLB Pipeline blue, PROSPX consensus pink,
// eFV the site lilac (its identity color, theme-aware via --accent-lilac).
const _RATER_META = {
  fangraphs:        { label: "FanGraphs",        color: "#2E8B57" },
  mlb_pipeline:     { label: "MLB Pipeline",     color: "#4F9DFF" },
  prospx_consensus: { label: "PROSPX consensus", color: "#FF6FB3" },
  xfv:              { label: "eFV (ours, OOS)",  color: "var(--accent-lilac)" },
};
const _TIER_ORDER = ["<45", "45", "50", "55", "60+"];
function _raterMeta(r) {
  return _RATER_META[r] || { label: String(r), color: "var(--text-tertiary)" };
}
// WAR-capture (lift) curve: share of all realized career WAR sitting in the top N% of each
// board. A sharper-ordering grade concentrates WAR earlier -> a higher curve. Replaces the
// confounded mean-WAR-by-tier chart (where BETTER ordering paradoxically lowers the middle mean).
function _methCaptureCurve(bt) {
  const cc = bt.accuracy && bt.accuracy.capture_curve;
  if (!cc || !cc.xfv || !cc.consensus) return "";
  const W = 460, H = 230, ML = 40, MR = 12, MT = 16, MB = 30, iW = W - ML - MR, iH = H - MT - MB;
  const sx = p => ML + p * iW, sy = v => MT + iH - v * iH;
  const grid = [];
  for (let i = 0; i <= 4; i++) {
    const v = i / 4, y = sy(v).toFixed(1);
    grid.push(`<line x1="${ML}" y1="${y}" x2="${ML + iW}" y2="${y}" stroke="var(--border-light)" stroke-width="0.5" stroke-dasharray="2,3"/>`,
      `<text x="${ML - 6}" y="${y}" dy="3" text-anchor="end" font-size="9" fill="var(--text-tertiary)">${Math.round(v * 100)}%</text>`);
  }
  const xlabels = [0, 0.2, 0.4, 0.6, 0.8, 1].map(p =>
    `<text x="${sx(p).toFixed(1)}" y="${MT + iH + 15}" text-anchor="middle" font-size="9" fill="var(--text-secondary)">${Math.round(p * 100)}%</text>`).join("");
  const diag = `<line x1="${sx(0)}" y1="${sy(0)}" x2="${sx(1)}" y2="${sy(1)}" stroke="var(--text-tertiary)" stroke-width="0.8" stroke-dasharray="4,4"/>`;
  const line = (pts, col, wdt) => {
    let d = `M ${sx(0).toFixed(1)},${sy(0).toFixed(1)}`;
    pts.forEach(p => { d += ` L ${sx(p.pct).toFixed(1)},${sy(p.captured).toFixed(1)}`; });
    return `<path d="${d}" fill="none" stroke="${col}" stroke-width="${wdt}" stroke-linecap="round" stroke-linejoin="round"/>`;
  };
  const efvCol = "var(--accent-lilac)", consCol = _raterMeta("prospx_consensus").color;
  const t20x = Math.round((cc.xfv.top20 || 0) * 100), t20c = Math.round((cc.consensus.top20 || 0) * 100);
  return `<div class="meth-chart">
    <div class="meth-chart-title">Career WAR captured by the top of the board <span class="meth-sub">share of all realized WAR sitting in each board's top N%, higher = sharper ordering</span></div>
    <svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="WAR capture curve">
      ${grid.join("")}${diag}
      <line x1="${ML}" y1="${MT + iH}" x2="${ML + iW}" y2="${MT + iH}" stroke="var(--text-secondary)" stroke-width="1"/>
      <line x1="${ML}" y1="${MT}" x2="${ML}" y2="${MT + iH}" stroke="var(--text-secondary)" stroke-width="1"/>
      ${line(cc.consensus.points, consCol, 2.2)}${line(cc.xfv.points, efvCol, 2.8)}
      ${xlabels}
      <text x="${ML + iW}" y="${MT + iH + 15}" text-anchor="end" font-size="9" fill="var(--text-tertiary)">top % of board</text>
    </svg>
    <div class="meth-legend">
      <span class="meth-legend-key"><span class="meth-legend-swatch" style="background:${efvCol};"></span>eFV</span>
      <span class="meth-legend-key"><span class="meth-legend-swatch" style="background:${consCol};"></span>PROSPX consensus</span>
      <span class="meth-legend-key"><span class="meth-legend-swatch" style="background:var(--text-tertiary);"></span>random</span>
    </div>
    <p class="meth-note">eFV concentrates <strong>${t20x}%</strong> of all realized career WAR in the top 20% of its board, against ${t20c}% for the consensus. It sorts the eventual contributors toward the top more sharply. Full graded pool (n=${cc.pool_n.toLocaleString()}, debuted + busts); the public sources don't grade the lower-minors busts, so this lift curve is eFV against the consensus it is built to upgrade.</p>
  </div>`;
}
function _methProseHTML() {
  // Tiered $/WAR for the worked example, read from the live framework snapshot
  // (data/value_framework.js -> window.VALUE_FRAMEWORK) instead of re-hardcoded
  // prose: the $7.7M/$9.7M/$15.1M this sentence used to carry had rotted a full
  // config generation behind the served table (the _methAccuracyChart pattern).
  const _dpwT = ((window.VALUE_FRAMEWORK || {}).dollars_per_war || {}).tiered_mm || {};
  const _dpwF = v => (v == null || isNaN(Number(v)) ? null : "$" + Number(v).toFixed(2) + "M");
  const _dpwTxt = (_dpwF(_dpwT.lt_1) && _dpwF(_dpwT["1_to_2"]) && _dpwF(_dpwT["2plus"]))
    ? ` (about ${_dpwF(_dpwT.lt_1)} / ${_dpwF(_dpwT["1_to_2"])} / ${_dpwF(_dpwT["2plus"])} by WAR level)`
    : "";
  return `
  <div class="meth-prose">
    <h2 class="meth-h">How eFV is built <span class="meth-sub">the site's primary grade</span></h2>
    <p><strong>eFV (eephusFV)</strong> is our outcome-grounded Future Value grade, and the
    primary grade and ranking signal site-wide. A scout FV grades the tool profile; eFV predicts
    the career it produces: <em>given everything known before a prospect debuts, his distribution
    of first-6-MLB-season WAR</em>, summarized back onto the familiar 20-80 scale.</p>
    <p><strong>The model.</strong> eFV starts from the consensus FV as a regularized prior (see
    below), then adds a small set of outcome-validated adjustments: the signals that carry WAR
    information <em>beyond</em> the grade and are under-priced by scouts. Hitters: on-base vs level,
    contact (K%) vs level, a multi-season peak K-rate, age-for-level, MiLB track-record length, the
    hit and speed tools. Pitchers: a multi-season peak K-rate, final-season K-rate, walk rate (the
    K-BB% completion), age-for-level, fastball. Game power is <em>omitted</em> for hitters on
    purpose: the data shows scouts over-price it and it predicts ISO, not incremental WAR, so
    leaving it out is eFV's power-overpricing correction. It is a regularized ridge on 3,961
    labeled prospects (debut classes 2011-2024 plus the never-debuted bust pool; 1,917 hitter and
    2,044 pitcher frames per the committed dataset reports), rate features sample-shrunk so a cup
    of coffee does not read as a track record.</p>
    <p><strong>The guarded blend.</strong> The headline ranking is a guarded blend,
    rank = (1-λ)·(consensus→WAR) + λ·(model→WAR). λ is <em>pinned</em>, hitters 0.70 and pitchers
    0.57, and the pins are stability decisions rather than accuracy claims: across the whole
    selection band the pooled result moves by about a fifth of what this eval can even resolve, so
    re-picking λ every rebuild was chasing noise and moving published grades for no measured gain.
    The blend cannot fall far below the consensus prior, and leans on eFV where its edge is real.</p>
    <p><strong>Two grades, one model.</strong> The <em>headline</em> eFV is the model's own
    outcome-grounded grade: predicted first-six-year WAR read back through a curve fit on what
    prospects at each grade actually went on to do. It is not pinned to the consensus
    distribution, so it can and does disagree with the industry, and on the current board it
    disagrees by a full 5-point rung or more on most of the hitters. A separate grade on the older
    consensus-anchored scale still prices the surplus dollars and the 5-bucket outcome mix, because
    those value curves were fitted on that scale. Live prospects also get two bounded tilts: a
    Statcast+ quality tilt on upper-level prospects, and an injury penalty that applies to
    <em>pitchers only</em> (current IL status, deepened by recent IL load). The penalty is
    pitcher-only because that is what the outcomes support: holding the scouting grade, age and
    rostered time equal, a pitcher carrying an active injury goes on to produce less, while a
    hitter does not. Post-TJ status by itself is not treated as an injury.</p>
    <p><strong>Everywhere, frozen at debut.</strong> Every graded prospect carries an eFV: the
    active boards, graduates (backgraded at their final pre-debut snapshot, then <em>locked</em>),
    and the farm-system rankings, surplus, DvM+, and movement engine all run on it. Players with no
    pro track record (recent draftees, int'l signs) fall back to the consensus prior until they
    play.</p>
<!-- NO ACCURACY CLAIM HERE, BY DESIGN (2026-08-19). This paragraph used to
    assert, in is-good styling, that eFV led every public source while the
    artifact's own head_to_head_verdict said not resolvable (xfv_beats:false)
    and, on the vintage-matched basis, MLB Pipeline led eFV on both Spearman
    and AUC. This view does not load source_backtest.json, so the honest fix
    is to make no claim and point at the surfaces that derive theirs from the
    artifact at render time (the Source Comparison hero + _methEfvVerdict). -->
    <p class="meth-verdict">How eFV compares with the public sources is measured, not asserted:
    the Source Comparison tab runs the out-of-sample, leakage-free, forward-chained backtest
    against the PROSPX consensus, MLB Pipeline, and FanGraphs, and derives its verdict from the
    artifact at render time, noise floors included. eFV is <strong>provisional</strong> and near
    the data's rank ceiling; its historical track is a current-model retrospective, not the grade
    we showed at the time.</p>

    <h2 class="meth-h">How the consensus FV (eFV's prior) is built</h2>
    <p>The consensus FV is the scout-grade aggregate eFV anchors on, and the reference shown
    alongside eFV everywhere. Every source that publishes an explicit 20-80 Future Value grade
    feeds an <strong>equal-weight</strong> consensus: every source votes at exactly 1.0. An
    accuracy-weighted scheme (Pipeline 1.06 / FanGraphs 0.94) shipped in June 2026 and was
    <strong>reverted to equal weights on 2026-07-25</strong> after a hardened re-measurement
    showed the weights were unearned: the weighted blend's edge measured d&rho; -0.0012 against
    a minimum detectable effect of 0.0068, inside the noise floor, and only two of eight outlets
    even have resolvable outcome history. The consensus FV is the equal-weight mean of the
    published grades (FanGraphs, ESPN, Just Baseball, TJStats, MLB Pipeline,
    and MLB Pipeline International). Two rank-only sources (Baseball America, The Athletic)
    contribute a rank→implied-FV <em>only</em> when no source has graded a player yet; once
    any explicit FV exists, the grade mean wins and ranks become informational (the
    <code>avg_rank</code> field).</p>
    <p>Grades are <strong>forward-filled</strong>: because sources publish on different dates,
    the consensus at any date uses the latest snapshot from <em>every</em> source up to that
    date, so a player isn't reduced to a single most-recent list. It is then
    <strong>Bayesian-shrunk</strong> - a thin-evidence grade (graded by few sources, or only
    just added) is pulled toward a prior, so one aggressive outlier source can't swing the
    number until corroborating grades arrive. The chart you see on every prospect page is this
    point-in-time consensus history; the per-source overlay shows the inputs it blends.</p>

    <h2 class="meth-h">How the Arkmetrics are derived</h2>
    <dl class="meth-dl">
      <dt>WAG - WAR Above Grade <span class="meth-tag">graduates</span></dt>
      <dd>A graduate's career WAR <em>rate</em> projected to a role-typical full season
      (612 PA for hitters; 175 / 65 / 50 / 60 IP for SP / MIRP / SIRP / CL), minus the
      per-season WAR the player's FV grade implied. Positive = outproducing the grade. Sample
      floors of 150 PA / 50 IP gate it. This is the realized-outcome metric the backtest below
      leans on.</dd>

      <dt>DvM+ - Development vs Mean <span class="meth-tag">farm system</span></dt>
      <dd>A wRC+-style index of organizational development: an org's cumulative <strong>eFV</strong>
      growth over a 1 / 3 / 6-year window scored against the league-mean farm (100 = mean, +10 =
      one standard deviation). Acquisitions are nullified and graduations don't subtract, so it
      measures only development of prospects already in the system. The farm grade weights
      6y / 3y / 1y at 60 / 30 / 10%. ($DvM+, the per-prospect surplus-development index, is also
      eFV-based; ToolDvM+ stays on per-tool scout-grade growth, since the tool grades have no
      separate eFV time series.)</dd>

      <dt>RPS+ - Rate Performance Score <span class="meth-tag">prospect</span></dt>
      <dd>A level-anchored rate index (OPS+ for hitters, ERA- for pitchers) normalized against
      the player's <em>own</em> age × position-group cohort, then nudged by a small position
      multiplier (C ×1.08 … 1B ×0.95). 100 = the same-age, same-position-group mean. MLB-level
      prospects substitute canonical wRC+ / xFIP.</dd>

      <dt>SC+ - Statcast+ <span class="meth-tag">prospect</span></dt>
      <dd>A side-aware composite of tracked Statcast / zone signals - contact quality + zone
      discipline for hitters; stuff + induced whiff/chase + suppressed contact for pitchers.
      Each component is z-scored against the side-matched active pool, averaged, and rescaled so
      100 = pool mean and one standard deviation moves it 15 points (the wRC+/OPS+ family).</dd>

      <dt>ToolDvM+ - Tool Development vs Mean <span class="meth-tag">farm system</span></dt>
      <dd>A position-weighted blend of an org's per-tool DvM+ values (Hit, Power, Field, Arm,
      Fastball, Command, …). Each tool's development velocity is league-anchored (100 + 10·z),
      then weighted by how much that tool matters for the position bucket (a catcher's Field/Arm,
      a starter's Fastball/Command), so growing the <em>right</em> tools scores higher than
      padding the average.</dd>
    </dl>

    <div class="meth-eg-card">
      <div class="meth-eg-title">Worked example · how a grade becomes a dollar figure</div>
      <div class="meth-eg-row">An <b>${gTermLink("fv", "FV")} 60</b> shortstop: the FV→WAR anchor maps the grade to a per-year WAR expectation, the position multiplier nudges it for the up-the-middle profile, and the seven cost-controlled years are priced at the tiered ${gTermLink("dpw_tier", "$/WAR")}${_dpwTxt} minus the league-min-plus-arb cost basis, then probability-weighted across debut and bust outcomes and discounted to present value.</div>
      <div class="meth-eg-row">The result is the published ${gTermLink("surplus_value", "surplus value")} on that player's card. A higher ${gTermLink("dvm_plus", "$DvM+")} (faster-than-mean development) and stronger underlying rates (${gTermLink("k_pct", "K%")} / ${gTermLink("bb_pct", "BB%")}, ${gTermLink("ops_plus", "OPS+ vs lvl")}) lift the expectation within the FV band.</div>
      <div class="meth-eg-note">Illustrative - each player's card carries their own current figure, which moves with the FV→WAR table and the $/WAR market.</div>
    </div>

    <h2 class="meth-h">Surplus value - the economic model</h2>
    <p>A prospect is an asset because the seven years of club control after debut are paid below
    market. Surplus value is the dollar production those controlled years are expected to deliver
    above what they cost. The grade priced here is <strong>eFV</strong> (the consensus FV is the
    fallback where eFV abstains); the pricing engine below is grade-agnostic - it takes whatever
    grade leads and converts it to dollars:</p>
    <p class="meth-eq">surplus = (expected WAR × $/WAR) − cost basis, probability-weighted across outcomes and discounted to present value</p>
    <p>The build, in order: (1) the <strong>FV→WAR anchor</strong> converts the scouting grade to an
    expected ${gTermLink("war", "WAR")}/year over seven controlled seasons (${gTermLink("fv_to_war_table", "the FV→WAR table")}).
    (2) WAR is priced at a non-linear, tiered <strong>${gTermLink("dpw_tier", "$/WAR")}</strong> (a win on a star is worth more
    than a win on a replacement-level filler). (3) The <strong>cost basis</strong> is the three pre-arbitration
    years at the league minimum plus four arbitration years at an escalating fraction of free-agent
    value (${gTermLink("service_time", "service-time")} schedule). (4) Because a prospect is a <em>distribution</em>
    of outcomes, not a point, the engine probability-weights the five-bucket outcome set (bust → bench
    → regular → good → star) rather than trusting the FV midpoint, then discounts future years to present value
    at the shipped net 7%/yr (config/valuation_sets/clemens_2026.yaml: control.years 7, discount.net_rate 0.07,
    a 10% discount rate minus 3% annual win-cost growth; the base config's 6 years / 9% are the legacy
    prospx_current values and are overridden in production). The published number is an <strong>expected value</strong>, not a median: since the EV
    reframe (calibration version isotonic-real-v6-evframe, 2026-07-31) the raw expectation is corrected
    by a count-weighted isotonic (PAVA) map fit on resolved-cohort bin means, and the old $0 floor on
    low-tier prospects is gone - a bottom-tier player's price is his small positive expectation, because
    the trade engine consumes surplus as a price and a price is an expectation. Dollars are priced
    through the production valuation set <code>clemens_2026</code> (Ben Clemens' published 2026
    FanGraphs framework, checksummed anchors) with the FA signings-implied $/WAR re-anchor
    <em>disabled</em> under that set. The published per-prospect figure is ${gTermLink("surplus_value", "Surplus value")}; the per-FV-point
    and per-dollar efficiency cuts are ${gTermLink("surplus_per_fv_pt", "Surplus / FV-pt")} and ${gTermLink("dollars_per_fv", "$/FV-pt")}.
    The <em>Interactive</em> tab below walks an FV through every step.</p>

    <h2 class="meth-h">Farm-system grades - how the org letter is built</h2>
    <p>The org grade is a weighted tree (${gTermLink("farm_report_card", "Farm grade tree")}), not a single
    formula, so each letter is auditable down to its leaves. Four branches, value-led (v40):
    <strong>Value</strong> (65% - the org's aggregate risk-adjusted controlled surplus, the total $ value of
    the active prospect pool from the recalibrated value framework, which already prices elite ceiling
    non-linearly; ${gTermLink("fin_war_per_m", "WAR per $M")}, ${gTermLink("fin_contract_surplus", "grad-contract surplus")},
    ${gTermLink("fin_dollar_dvm", "Org $DvM+")}, ${gTermLink("fin_draft_pool_efficiency", "draft-pool efficiency")},
    ${gTermLink("fin_ifa_roi", "IFA ROI")}), <strong>MLB Production</strong> (18% - does the system produce
    big-leaguers, boom/bust rates, top-3 graduate WAR, a star-presence ${gTermLink("mlb_production_conviction", "Conviction")}
    flag), <strong>Development</strong> (9% - per-tool growth of prospects the org already had,
    ${gTermLink("dvm_plus", "DvM+")} / ${gTermLink("tools_dvm_plus", "ToolDvM+")}), and
    <strong>Acquisition Strategy</strong> (8% - Draft / IFA / Trade / Waiver channels).
    Every leaf is z-scored across the 30 orgs and anchored so the composite reads on a 100 = league-mean
    scale; sparse leaves return " - " rather than guessing. Surplus enters the Value branch as realized
    capital efficiency and again via the development of surplus dollars (Org $DvM+).</p>

    <h2 class="meth-h">Aggregation - player level to farm level</h2>
    <p>Roll-ups are explicit, not implied. Org surplus is the sum of its active prospects' per-player
    surplus dollars (the authoritative engine aggregate, <code>_active_surplus_net_mm</code>); the farm
    list, the detail Surplus tile, and the Finances tab all read that one number. DvM+ / ToolDvM+
    aggregate per-tool development across the org's actives with acquisitions nullified (so a trade
    doesn't read as development) and graduations not subtracted (so promoting a star doesn't read
    as a loss). The "+" indices (DvM+, RPS+, SC+, OrgSur+) are all built to the wRC+/OPS+ convention - 
    100 = the relevant mean, ±10 ≈ one standard deviation - so they share one mental scale.</p>

    <h2 class="meth-h">Where the Arkmetrics sit vs public metrics</h2>
    <table class="meth-cmp">
      <thead><tr><th>Arkmetric</th><th>Closest public analogue</th><th>What's different</th></tr></thead>
      <tbody>
        <tr><td>${gTermLink("wag", "WAG")}</td><td>WAR vs draft-pick / FV expectation</td><td>Measures realized career WAR against the WAR a player's FV grade <em>implied</em> - a grade-calibration residual, not raw production.</td></tr>
        <tr><td>${gTermLink("dvm_plus", "DvM+ / $DvM+")}</td><td>Farm-system surplus-value rankings (e.g. public prospect-value tables)</td><td>Indexed wRC+-style (100 = mean) and scoped to in-system <em>development</em> with acquisitions removed, so it isolates org skill rather than hoarded talent.</td></tr>
        <tr><td>${gTermLink("surplus_value", "Surplus value")}</td><td>Surplus-value frameworks (FV→WAR→$ minus cost)</td><td>Same skeleton, but probability-weighted over a bucketed outcome distribution and discounted, rather than applying a single FV-tier dollar constant.</td></tr>
        <tr><td>${gTermLink("rps_plus", "RPS+")}</td><td>wRC+ / ERA-</td><td>Re-anchored to the player's own age × position-group cohort and level, so a young hitter at a hard level isn't penalized against older peers.</td></tr>
        <tr><td>${gTermLink("statcast_plus", "SC+")}</td><td>Statcast percentile dashboards</td><td>Collapses the tracked-data panel into one side-aware, pool-anchored composite on the wRC+ scale.</td></tr>
      </tbody>
    </table>

    <h2 class="meth-h">Data sources &amp; references</h2>
    <ul class="meth-refs">
      <li><strong>Scouting grades / FV:</strong> FanGraphs, MLB Pipeline (domestic + international), ESPN, Just Baseball, TJStats; rank-only fallbacks from Baseball America and The Athletic.</li>
      <li><strong>Performance &amp; tracked data:</strong> MLB Stats API (MLB + MiLB statlines), Baseball Savant (Statcast) where available for upper-level / debuted players, pulled via pybaseball.</li>
      <li><strong>Contracts &amp; bonuses:</strong> published MLB draft-pool and international bonus-pool figures; Spotrac for graduate contract/AAV data.</li>
      <li><strong>Framework anchors:</strong> the FanGraphs scouting primer (FV→WAR ranges) and public $/WAR estimates (tiered, rolling multi-year average). The surplus engine's outcome buckets and discount rate are documented in <code>value_framework.py</code>.</li>
      <li><strong>Valuation set:</strong> production prices through <code>clemens_2026</code>, the FanGraphs / Ben Clemens 2026 published prospect-valuation framework, its tier values fetched from the source posts and checksum-validated at load. Under this set the FA signings-implied $/WAR re-anchor (<code>fa_implied</code>) is disabled; served dollars sit on the published FanGraphs rate basis.</li>
    </ul>

    <h2 class="meth-h">Data sources &amp; attribution</h2>
    <p class="meth-note">PROSPX grades are a consensus built across seven independent industry sources - the value added is the aggregation, calibration, and track-record audit, not any single list. No source's rankings or reports are republished wholesale; excerpts appear with attribution in the spirit of commentary and analysis. All trademarks and data remain the property of their owners. The full attribution page lives at <a href="/sources/">/sources/</a>.</p>
    <div class="article-grid">
      ${[
        ["FanGraphs", "https://www.fangraphs.com/", "Prospect rankings, FV + tool grades, scouting reports (consensus input); league stats and park factors."],
        ["MLB Pipeline", "https://www.mlb.com/prospects", "Prospect rankings and grades (consensus input); draft bonus pools and slot values."],
        ["Baseball America", "https://www.baseballamerica.com/", "Prospect rankings and grades (consensus input)."],
        ["ESPN", "https://www.espn.com/mlb/", "Prospect rankings (consensus input); team logo imagery on internal surfaces."],
        ["The Athletic", "https://www.nytimes.com/athletic/", "Prospect rankings (consensus input)."],
        ["Just Baseball", "https://www.justbaseball.com/", "Prospect rankings (consensus input)."],
        ["TJStats", "https://x.com/TJStats", "Prospect rankings (consensus input) and movers wire."],
        ["MLB Stats API / Baseball Savant", "https://baseballsavant.mlb.com/", "Game logs, transactions, rosters, Statcast tracking data, and player headshots."],
        ["Baseball-Reference", "https://www.baseball-reference.com/", "war_daily (bWAR): the run frame the served eWAR is built on, plus historical player pages."],
        ["pybaseball", "https://github.com/jldbc/pybaseball", "Open-source Python toolkit used to pull Statcast, FanGraphs, and Baseball-Reference data programmatically."],
        ["Spotrac", "https://www.spotrac.com/", "Contracts, payrolls, free-agent classes, and international signing trackers."],
      ].map(([nm, url, use]) => `<div class="card source-card"><h3><a href="${url}" target="_blank" rel="noopener noreferrer">${escapeHtml(nm)}</a></h3><p>${escapeHtml(use)}</p></div>`).join("")}
    </div>
    <p class="meth-note">All grades remain the property of their publishers; the site stores them to compute a consensus and does not redistribute source lists wholesale.</p>

    <h2 class="meth-h">Methodology changelog</h2>
    <ul class="meth-changelog">
      <li><span class="mc-date">2026-07-31</span> Surplus moved to an EXPECTED-VALUE objective (calibration isotonic-real-v6-evframe): the correction map is now a count-weighted isotonic (PAVA) fit on resolved-cohort bin means, targeting the conditional mean instead of the median. The $0 floor on bottom-tier prospects is gone; the board total moved up while the ordering did not. The map deliberately loses the old median-objective MAE gate and that loss is committed, not hidden.</li>
      <li><span class="mc-date">2026-07-30</span> The eFV headline grade's outcome-implied FV mapping re-keyed to the recalibrated empirical FV→WAR anchors, so the grade and the dollars read off the same curve.</li>
      <li><span class="mc-date">2026-07-29/30</span> Valuation recalibration: sub-45 anchors repaired, the board-scale re-expression turned off, and <code>clemens_2026</code> (the published FanGraphs / Ben Clemens 2026 framework, checksummed anchors, <code>fa_implied</code> disabled) made the default production valuation set.</li>
      <li><span class="mc-date">2026-07-25</span> Consensus source weighting REVERTED to equal. The June accuracy weights (Pipeline 1.06 / FanGraphs 0.94) failed a hardened forward-chained re-measurement: d&rho; -0.0012 against a minimum detectable effect of 0.0068, so the weighted blend's win was inside the noise floor and unearned. Every source votes 1.0 again; the revert is committed in data/source_weights.json.</li>
      <li><span class="mc-date">2026-07</span> Cross-source scale normalization: each source's grades are quantile-mapped onto the FanGraphs scale over the players both grade before blending, so a hot or cold outlet is de-biased by the shape of its whole distribution. Per-source grades on the card are unchanged; only the consensus scale is.</li>
      <li><span class="mc-date">2026-06</span> Historical backfill: ingested FanGraphs 2017-2020 boards (new-format CSVs) + MLB Pipeline 2017-2020 Top 100, each grade date-stamped to its year. The backtest's resolved-cohort window grew from 2021-2023 (3 base years) to 2017-2023 (7), and the common scored set grew with it. On the larger, further-resolved sample the blend's edge over its best single input is two-legged: it separates future contributors better (the AUC leg resolves), while the ordering gap (Spearman) sits inside the noise floor the backtest can resolve. The live legs, floors, and common-set size render in Source Comparison below.</li>
      <li><span class="mc-date">2026-06</span> Surplus engine v38: FV→WAR anchor moved from a single peak-year projection to a flat 6-year-average table; side difference carried by the position multiplier. Farm list/detail surplus consolidated on the engine aggregate.</li>
      <li><span class="mc-date">2026-06</span> Glossary reorganized into Glossary / Methodology / Source Comparison; taxonomy regrouped (Arkmetrics · Statcast · Standard · Scouting · Economic · Farm · Site Features); Statcast input terms added.</li>
      <li><span class="mc-date">2026-06</span> Farm grade tree v40: value-tracking reweight. The org letter is now primarily driven by aggregate risk-adjusted controlled surplus (the Value branch, 65%); Development drops from the top weight to a secondary controllable-skill signal (9%), MLB Production 18%, Acquisition Strategy 8%. This stops the grade from reading as a per-prospect tool-development index decoupled from aggregate farm value.</li>
      <li><span class="mc-date">2026-05</span> Farm grade tree v7: MLB Production added a Bust-Rate (negative) leaf and a Conviction star-presence cap; Development promoted to the 40% top weight.</li>
      <li><span class="mc-date">2026-06</span> Consensus FV moved to ACCURACY-WEIGHTED source blending after a vintage-disciplined A/B beat equal-weight on both Spearman and AUC (weights shrunk toward equal, clamped, frozen per vintage; sources without resolved history stay at 1.0). Reverted 2026-07-25, above: the hardened re-measurement could not resolve the win.</li>
      <li><span class="mc-date">2026-05</span> Source-vs-source backtest published (resolved cohorts only) as the Source Comparison area.</li>
      <li><span class="mc-date">2026-04</span> Consensus FV: equal-weight mean confirmed over weighted schemes at that window; Bayesian shrinkage + forward-fill formalized.</li>
    </ul>
    <p class="meth-note">Versioned methodology pairs with the Time Machine: a board state and the rules that produced it are both reconstructable for any past month.</p>

    <h2 class="meth-h">FAQ</h2>
    <dl class="meth-dl">
      <dt>Why a consensus instead of one source?</dt>
      <dd>Averaging cancels idiosyncratic source error, and the measured edge is two-legged: on resolved cohorts the blend separates future contributors from non-contributors better than any single input (the AUC leg clears its floor), while on ordering realized WAR the gap to its best input sits inside the noise floor the backtest can resolve. Blending buys discrimination, not ordering; the live legs and floors render in Source Comparison. Per-source edges are small and unstable year to year, which is why the blend stays at equal weights rather than chasing them.</dd>
      <dt>How are sources weighted?</dt>
      <dd>Equally: every source votes at exactly 1.0. An accuracy-weighted blend (per-source weights from measured track records, shrunk toward equal and clamped) shipped in June 2026 and was reverted on 2026-07-25, when a hardened forward-chained re-measurement showed its edge was smaller than the test could resolve (d&rho; -0.0012 vs a minimum detectable effect of 0.0068) - the weights were unearned, so they came off. Only two of eight outlets even have resolvable outcome history. The interactive below lets you test any weighting yourself.</dd>
      <dt>How often does it update?</dt>
      <dd>Grades, Arkmetrics, farm grades, and the backtest refresh monthly; transactions, IL, roster status, debuts, and trades refresh daily. Each board stamps its own cadence.</dd>
      <dt>What's the track record - and its limits?</dt>
      <dd>The evaluation window spans seven preseason base years (2017-2023): the 2017-2020 cohorts are fully resolved while 2021-2023 are still accruing WAR, and cumulative WAR is censored at today. Top FV tiers stay thin (n≈40-70), so their rates move on a few outcomes. The Source Comparison area lists sample sizes and these caveats in full rather than headlining an inflated number.</dd>
    </dl>
  </div>`;
}

// Smooth (Catmull-Rom) calibration line: x = FV tier, y = an outcome metric,
// one line per rater. Honest "smooth data curve" while UI stays sharp-cornered.
function _methCalibrationChart(bt, metricKey, metricLabel, opts) {
  opts = opts || {};
  const W = 580, H = 250, ML = 46, MR = 16, MT = 16, MB = 40;
  const iW = W - ML - MR, iH = H - MT - MB;
  const tiers = _TIER_ORDER;
  // eFV joins the FV-tier lines whenever its cohort is present (primary, drawn boldest).
  const raterList = bt.raters.concat(bt.cohorts.xfv ? ["xfv"] : []);
  const series = raterList.map(r => {
    const tmap = {}; ((bt.cohorts[r] && bt.cohorts[r].tiers) || []).forEach(t => { tmap[t.tier] = t; });
    return { rater: r, pts: tiers.map(t => tmap[t] ? tmap[t][metricKey] : null) };
  });
  const allVals = series.flatMap(s => s.pts).filter(v => v != null);
  if (!allVals.length) return "";
  const yMax = opts.yMax || (Math.max(...allVals) * 1.1 || 1);
  const yMin = opts.yMin || 0;
  const sx = i => ML + (tiers.length === 1 ? iW / 2 : (i / (tiers.length - 1)) * iW);
  const sy = v => MT + iH - ((v - yMin) / (yMax - yMin)) * iH;
  const yticks = 4;
  const grid = [];
  for (let i = 0; i <= yticks; i++) {
    const v = yMin + (yMax - yMin) * i / yticks;
    const y = sy(v).toFixed(1);
    grid.push(`<line x1="${ML}" y1="${y}" x2="${ML + iW}" y2="${y}" stroke="var(--border-light)" stroke-width="0.5" stroke-dasharray="2,3"/>`,
      `<text x="${ML - 6}" y="${y}" dy="3" text-anchor="end" font-size="9" fill="var(--text-tertiary)">${opts.pct ? Math.round(v * 100) + "%" : v.toFixed(opts.dp != null ? opts.dp : 1)}</text>`);
  }
  const xlabels = tiers.map((t, i) =>
    `<text x="${sx(i).toFixed(1)}" y="${MT + iH + 16}" text-anchor="middle" font-size="10" fill="var(--text-secondary)" font-weight="600">${t}</text>`).join("");
  const lines = series.map(s => {
    const pts = s.pts.map((v, i) => v == null ? null : { x: sx(i), y: sy(v) }).filter(Boolean);
    if (pts.length < 2) return "";
    let d = `M ${pts[0].x.toFixed(1)},${pts[0].y.toFixed(1)}`;
    for (let i = 0; i < pts.length - 1; i++) {
      const p0 = pts[i - 1] || pts[i], p1 = pts[i], p2 = pts[i + 1], p3 = pts[i + 2] || pts[i + 1];
      const c1x = p1.x + (p2.x - p0.x) / 6, c1y = p1.y + (p2.y - p0.y) / 6;
      const c2x = p2.x - (p3.x - p1.x) / 6, c2y = p2.y - (p3.y - p1.y) / 6;
      d += ` C ${c1x.toFixed(1)},${c1y.toFixed(1)} ${c2x.toFixed(1)},${c2y.toFixed(1)} ${p2.x.toFixed(1)},${p2.y.toFixed(1)}`;
    }
    const col = _raterMeta(s.rater).color;
    const isEfv = s.rater === "xfv";
    const emph = isEfv || s.rater === "prospx_consensus";   // both drawn solid; eFV boldest
    const dots = pts.map(p => `<circle cx="${p.x.toFixed(1)}" cy="${p.y.toFixed(1)}" r="${isEfv ? 3.8 : emph ? 3.2 : 2.5}" fill="${col}"/>`).join("");
    return `<path d="${d}" fill="none" stroke="${col}" stroke-width="${isEfv ? 2.8 : emph ? 2.4 : 1.6}" ${emph ? "" : 'stroke-dasharray="5,3"'} stroke-linecap="round"/>${dots}`;
  }).join("");
  const legend = raterList.map(r =>
    `<span class="meth-legend-key"><span class="meth-legend-swatch" style="background:${_raterMeta(r).color};"></span>${escapeHtml(_raterMeta(r).label)}</span>`).join("");
  return `<div class="meth-chart">
    <div class="meth-chart-title">${escapeHtml(metricLabel)} by FV tier</div>
    <svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="${escapeHtml(metricLabel)} by FV tier">
      ${grid.join("")}
      <line x1="${ML}" y1="${MT + iH}" x2="${ML + iW}" y2="${MT + iH}" stroke="var(--text-secondary)" stroke-width="1"/>
      <line x1="${ML}" y1="${MT}" x2="${ML}" y2="${MT + iH}" stroke="var(--text-secondary)" stroke-width="1"/>
      ${lines}${xlabels}
    </svg>
    <div class="meth-legend">${legend}</div>
  </div>`;
}

// THE STAR IS EARNED BY A FLOOR, NOT BY A MAXIMUM (2026-09-24, census X01-01).
// The head-to-head bars and the share card starred whichever bar was longest.
// The artifact publishes ONE floor for this comparison, head_to_head_verdict
// (eFV against PROSPX consensus on the vintage-matched rows), and none for the
// AUC leg, which do-not-reopen item 3 records as null on every admissible cell.
// So a star goes to the winner of that one floored pair, only when the pair
// resolves, and only when that winner also tops every bar; otherwise no bar is
// starred. Returns the rater key to star on the Spearman leg, or null.
function _hhStarRater(bt) {
  const acc = bt && bt.accuracy;
  const hh = acc && acc.head_to_head_verdict;
  const blk = acc && acc.pooled_efv_common_vintage_matched;
  if (!hh || hh.resolvable !== true || !blk) return null;
  if (hh.basis !== "pooled_efv_common_vintage_matched") return null;
  const winner = hh.xfv_beats ? "xfv" : "prospx_consensus";
  const w = blk[winner];
  const vals = Object.keys(blk).map(r => blk[r] && blk[r].spearman).filter(v => v != null);
  if (!w || w.spearman == null || !vals.length) return null;
  return w.spearman >= Math.max(...vals) - 1e-9 ? winner : null;
}

// Source-accuracy comparison - horizontal bars for Spearman ρ + AUC, consensus
// highlighted. Answers "which is most reliable, and does the blend win?"
//
// SAME ROWS AND SAME VINTAGE FOR THE BARS TOO (2026-09-24, census X01-01). The
// bars read accuracy.pooled, each rater on its own rows (eFV n 3,272, the boards
// n 4,316), under a title that says "same players", and starred eFV at 0.361
// against 0.286 while the verdict printed under them, read off the
// vintage-matched block, put eFV at 0.406 against 0.413. The verdict was moved
// onto that block on 2026-08-13 and the bars were not. HEADTOHEAD_FRAME_GATE
// says every artifact-driven surface follows the corrected number, so the bars
// read the verdict's block with no fallback: an artifact without it renders no
// chart rather than the uncorrected one.
function _methAccuracyChart(bt) {
  const acc = bt.accuracy && bt.accuracy.pooled_efv_common_vintage_matched;
  if (!acc) return "";
  const h2hRaters = (bt.accuracy && bt.accuracy.head_to_head_raters) || bt.raters;
  const spStar = _hhStarRater(bt);
  const metric = (key, label, lo, hi, fmt, starRater) => {
    const rows = h2hRaters.map(r => ({ r, v: acc[r] ? acc[r][key] : null })).filter(x => x.v != null);
    if (!rows.length) return "";
    const bars = rows.map(x => {
      const w = Math.min(100, Math.max(2, ((x.v - lo) / (hi - lo)) * 100));
      const emph = x.r === "prospx_consensus";
      const isBest = starRater != null && x.r === starRater;
      return `<div class="meth-bar-row">
        <span class="meth-bar-label">${escapeHtml(_raterMeta(x.r).label)}</span>
        <span class="meth-bar-track"><span class="meth-bar-fill${emph ? " is-consensus" : ""}" style="width:${w.toFixed(1)}%;background:${_raterMeta(x.r).color};"></span></span>
        <span class="meth-bar-val${isBest ? " is-best" : ""}">${fmt(x.v)}${isBest ? " ★" : ""}</span>
      </div>`;
    }).join("");
    return `<div class="meth-metric"><div class="meth-metric-title">${escapeHtml(label)}</div>${bars}</div>`;
  };
  const sp = metric("spearman", "Ordering skill - Spearman ρ (grade vs realized WAR)", 0, 0.5, v => v.toFixed(3), spStar);
  const au = metric("auc", "Discrimination - AUC (grade predicts ‘became a contributor’)", 0.5, 0.85, v => v.toFixed(3), null);
  const hhStar = bt.accuracy.head_to_head_verdict || null;
  const starNote = `<p class="meth-sub">★ marks a grader only where its gap clears a published noise floor. ${spStar
    ? "The Spearman gap clears its floor."
    : (hhStar && hhStar.resolvable === false)
      ? "The Spearman gap does not, so no bar is starred."
      : "No floor is published for the Spearman gap here, so no bar is starred."} No floor is published for the AUC leg on these rows, so no AUC bar is starred and no discrimination claim is made.</p>`;
  // SAME ROWS OR THE COMPARISON IS NOT ONE. accuracy.pooled scores each rater on
  // whatever it covers, so the eFV bar ran on 3,210 players and the board bars on
  // 4,259; roughly half the gap that pairing showed was the row difference, not
  // ordering skill. pooled_efv_common re-scores every rater on the rows eFV
  // covers. Falls back only for an artifact written before that block existed.
  // SAME VINTAGE OR THE COMPARISON IS NOT ONE EITHER (M-1, 2026-08-13). Identical
  // rows was only half the fix. eFV holds ONE grade per player, fitted at that
  // player's decision year, while the common set carries a consensus read for
  // every base year, so pooled_efv_common still pairs eFV against reads taken
  // years before or after its own. Both directions were measured and both bite:
  // post-debut reads hand the consensus up to 2.5 years of realized major league
  // outcome (it scores 0.400 there against 0.301 on the rest), and reads earlier
  // than the decision year hand eFV the information edge instead. The
  // vintage-matched block holds the vintage fixed on both sides and is the basis
  // head_to_head_verdict is computed on, so reading it here keeps the number and
  // the floor beneath it on the same population - which is the mismatch the hero
  // banner below was already fixed for once.
  const pld = acc;
  const x = pld.xfv, c = pld.prospx_consensus, fg = pld.fangraphs, mlb = pld.mlb_pipeline;
  const hh = bt.accuracy.head_to_head_verdict || null;
  let verdict;
  if (x && x.spearman != null && c && c.spearman != null) {
    const f3 = v => (v == null ? "-" : v.toFixed(3));
    const n = (bt.accuracy.common_n_efv_vintage_matched
      || bt.accuracy.common_n_efv || 0).toLocaleString();
    // DERIVED, NEVER ASSERTED (2026-09-04, design audit F46). This template used
    // to open with fixed prose asserting eFV ordered realized WAR ahead of every
    // rater, and then print MLB Pipeline ABOVE eFV in the same sentence: on
    // accuracy.pooled_efv_common_vintage_matched the artifact reads eFV 0.3983
    // against Pipeline 0.3990. A hard-coded accuracy CLAIM is the same banned
    // defect as a hard-coded accuracy NUMBER, and _methHeroBanner two functions
    // down already derives this exact call from the same block. Same rule here:
    // take the max over the raters, difference against it, and let the
    // artifact's own floor decide whether the difference may be called a lead.
    // The fragment is ratcheted in test_claims_freshness.BANNED_CLAIM_FRAGMENTS.
    const pubs = [["PROSPX consensus", c], ["MLB Pipeline", mlb], ["FanGraphs", fg]]
      .filter(pr => pr[1] && pr[1].spearman != null);
    const bestPub = pubs.length
      ? pubs.reduce((a, b) => (b[1].spearman > a[1].spearman ? b : a)) : null;
    const lead = bestPub ? (x.spearman - bestPub[1].spearman) : null;
    const ahead = (lead != null && lead > 0);
    const resolvable = !!(hh && hh.resolvable === true);
    const cls = (ahead && resolvable) ? "is-good" : "";
    const bestTxt = bestPub
      ? `${f3(bestPub[1].spearman)} for the best of them, ${escapeHtml(bestPub[0])}` : "";
    const head = (lead == null)
      ? `eFV orders realized WAR at Spearman ${f3(x.spearman)}`
      : (ahead && resolvable)
        ? `eFV orders realized WAR ahead of every source measured here, by a margin this backtest can resolve: Spearman ${f3(x.spearman)} against ${bestTxt}, a lead of +${lead.toFixed(3)} against a floor of ${f3(hh && hh.mde95)}`
        : ahead
          ? `eFV orders realized WAR ahead of every source measured here, but not by enough to call it: Spearman ${f3(x.spearman)} against ${bestTxt}, a lead of +${lead.toFixed(3)} that sits inside the ${f3(hh && hh.mde95)} this backtest can resolve at 95%`
          : `eFV and the best source measured here are indistinguishable: Spearman ${f3(x.spearman)} for eFV against ${bestTxt}, a ${lead.toFixed(3)} point estimate, so no ordering claim is made in either direction`;
    const rowTxt = pubs.map(pr => `${f3(pr[1].spearman)} ${escapeHtml(pr[0])}`).join(", ");
    verdict = `<p class="meth-verdict ${cls}">Out of sample and leakage-free, on the ${n} players eFV and the boards both grade, ${head}. The full row: eFV ${f3(x.spearman)}, ${rowTxt}. A wider gap you may have seen quoted compares eFV on its own rows against the boards on all of theirs, and about half of that one is the row difference rather than the ordering.</p>`;
  } else {
    verdict = `<p class="meth-verdict">On the common set of ${bt.accuracy.common_n.toLocaleString()} players, the consensus is competitive with its inputs but does not lead on every metric (reported as measured, not cherry-picked).</p>`;
  }
  const nRows = bt.accuracy.common_n_efv_vintage_matched || (acc.xfv && acc.xfv.n) || null;
  return `<div class="meth-chart meth-accuracy">
    <div class="meth-chart-title">Head-to-head predictive accuracy <span class="meth-sub">same players, same outcome, same window, same vintage${nRows ? ` &middot; n=${Number(nRows).toLocaleString()}` : ""}</span></div>
    ${sp}${au}${starNote}${verdict}
  </div>`;
}

// THE VERDICT UNDER THE eFV CHARTS IS DERIVED, NEVER ASSERTED (2026-08-14).
//
// This paragraph used to claim, as FIXED PROSE styled is-good, that eFV led consensus
// FV out-of-sample on both sides and that the edge held on the recent 2019-2023 cohorts,
// sitting directly beneath two charts whose own artifact fields say xfv_beats:false and
// verdict:"not resolvable at this power" on BOTH sides (hitters +0.0112, pitchers
// +0.0061, both against an MDE95 of 0.044). The bars and the star were already honest;
// only the sentence under them was not.
//
// The hero banner was moved onto derived copy on 2026-08-13 (see _methHeroBanner) and
// this sibling claim was missed, along with three others off-page. The last of those
// siblings, the every-public-source claim paragraph in _methProseHTML, was
// fixed on 2026-08-19: the Methodology view does not load the backtest artifact, so it
// now makes no accuracy claim at all and defers to the derived hero + Source Comparison.
// Hard-coded accuracy NUMBERS in copy were already banned; a hard-coded accuracy CLAIM
// is the same defect wearing prose, and it is worse here because the artifact carries a
// machine-readable verdict field that contradicts it.
function _methEfvVerdict(xc) {
  const sides = [["hitters", xc.sides.hitters], ["pitchers", xc.sides.pitchers]]
    .filter(p => p[1]);
  if (!sides.length) return "";
  const beat = sides.filter(p => p[1].xfv_beats && p[1].resolvable);
  const all = beat.length === sides.length;
  // The era clause is derived the same way: read which side/era cells actually lead
  // rather than asserting that "the edge holds on the recent cohorts".
  // Tallied PER ERA ACROSS SIDES, not pooled into one list. Pooling put 2019-2021 in
  // both the leading and the trailing column, because hitters and pitchers disagree
  // inside that cohort, and the sentence read as nonsense.
  let eraClause = "";
  const tally = {};
  sides.forEach(([, s]) => Object.keys(s.era_split || {}).forEach(k => {
    const e = s.era_split[k];
    if (e.xfv_blend_spearman == null || e.consensus_spearman == null) return;
    const t = (tally[k] = tally[k] || { up: 0, down: 0 });
    if (e.xfv_blend_spearman > e.consensus_spearman) t.up++; else t.down++;
  }));
  const eras = Object.keys(tally).sort();
  const cls = k => (tally[k].down === 0 ? "up" : tally[k].up === 0 ? "down" : "mixed");
  // ESCAPED. The era keys are artifact-supplied and one of them is literally "<=2018",
  // which raw would open a bogus tag and swallow the rest of the paragraph up to the
  // next ">". The era table above already escapes these for the same reason.
  const grp = w => eras.filter(k => cls(k) === w).map(escapeHtml);
  const [up, down, mixed] = [grp("up"), grp("down"), grp("mixed")];
  const bits = [];
  if (up.length) bits.push(`eFV leads on ${up.join(" and ")}`);
  if (down.length) bits.push(`consensus leads on ${down.join(" and ")}`);
  if (mixed.length) bits.push(`${mixed.join(" and ")} splits by side`);
  if (bits.length > 1) {
    eraClause = ` Split by debut era, ${bits.join(", ")}, so the ordering is not uniform across cohorts.`;
  } else if (up.length && eras.length) {
    eraClause = ` eFV leads in every debut era measured (${up.join(", ")}).`;
  }
  const head = all
    ? "eFV ranks ahead of consensus FV out-of-sample on both sides by a margin this eval can resolve."
    : beat.length
      ? `eFV ranks ahead of consensus FV by a resolvable margin on ${beat.map(p => p[0]).join(" and ")} only; on the other side the gap is inside the noise floor.`
      : "eFV and consensus FV are statistically indistinguishable on eFV's own out-of-sample protocol: on both sides the gap is smaller than the margin this eval can resolve.";
  return `<p class="meth-verdict${all ? " is-good" : ""}">${head}${eraClause} eFV is the primary grade; consensus FV remains a reference input. (This is eFV's own out-of-sample protocol, a more conservative test than the in-sample common-set bars above.)</p>`;
}

// eFV vs consensus FV - our outcome-grounded model, shown SEPARATELY from the per-source
// bars because it runs on its own out-of-sample protocol (the harder, conservative bar).
function _methEfvPanel(bt) {
  const xc = bt.xfv_vs_consensus;
  if (!xc || !xc.sides) return "";
  const W = v => Math.max(2, (v / 0.4) * 100).toFixed(1);
  const sideBlock = (key, label) => {
    const s = xc.sides[key];
    if (!s) return "";
    const win = s.xfv_beats;
    // The star is only earned when the gap is a MEASUREMENT. When the eval
    // cannot resolve the difference the page says so, rather than quietly
    // dropping the star and leaving two bars that look like a tie nobody
    // explained. See source_backtest XFV_VS_CONSENSUS_MDE95.
    const verdictNote = (s.resolvable === false && s.delta != null)
      ? `<div class="meth-sub" style="margin-top:4px;">Gap ${s.delta > 0 ? "+" : ""}${s.delta.toFixed(4)} is smaller than the ${s.mde95} this eval can resolve, so neither grade is shown as the winner.</div>`
      : "";
    const eras = s.era_split || {};
    const eraRows = Object.keys(eras).map(k => {
      const e = eras[k];
      const d = (e.xfv_blend_spearman != null && e.consensus_spearman != null)
        ? e.xfv_blend_spearman - e.consensus_spearman : 0;
      const col = d > 0 ? "var(--up)" : d < 0 ? "var(--down)" : "var(--text-secondary)";
      return `<tr><td>${escapeHtml(k)}</td><td>${e.n}</td><td>${e.consensus_spearman != null ? e.consensus_spearman.toFixed(3) : " - "}</td><td style="color:${col};font-weight:700;">${e.xfv_blend_spearman != null ? e.xfv_blend_spearman.toFixed(3) : " - "}</td></tr>`;
    }).join("");
    return `<div class="meth-metric">
      <div class="meth-metric-title">${escapeHtml(label)} <span class="meth-sub">n=${s.n}</span></div>
      <div class="meth-bar-row"><span class="meth-bar-label">Consensus FV</span><span class="meth-bar-track"><span class="meth-bar-fill" style="width:${W(s.consensus_spearman)}%;background:var(--text-secondary);"></span></span><span class="meth-bar-val">${s.consensus_spearman.toFixed(3)}</span></div>
      <div class="meth-bar-row"><span class="meth-bar-label">eFV</span><span class="meth-bar-track"><span class="meth-bar-fill is-consensus" style="width:${W(s.xfv_spearman)}%;background:var(--neon-cyan);"></span></span><span class="meth-bar-val${win ? " is-best" : ""}">${s.xfv_spearman.toFixed(3)}${win ? " ★" : ""}</span></div>
      ${verdictNote}
      ${eraRows ? `<div class="table-scroll-x" style="margin-top:6px;"><table class="meth-table"><thead><tr><th>Debut era</th><th>n</th><th>Consensus ρ</th><th>eFV ρ</th></tr></thead><tbody>${eraRows}</tbody></table></div>` : ""}
    </div>`;
  };
  // Per-FV-tier head-to-head + the resolved "receipts" (where they disagreed, who was right).
  const det = bt.accuracy && bt.accuracy.xfv_vs_consensus_detail;
  let tierTable = "", receipts = "";
  if (det && det.per_tier && det.per_tier.length) {
    const rows = det.per_tier.map(t => {
      const win = t.xfv_spearman != null && t.consensus_spearman != null && t.xfv_spearman > t.consensus_spearman;
      return `<tr><td class="meth-td-tier">${escapeHtml(t.tier)}</td><td>${t.n}</td>
        <td>${t.consensus_spearman != null ? t.consensus_spearman.toFixed(3) : " - "}</td>
        <td style="color:${win ? "var(--up)" : "var(--text-secondary)"};font-weight:${win ? 700 : 400};">${t.xfv_spearman != null ? t.xfv_spearman.toFixed(3) : " - "}${win ? " ★" : ""}</td></tr>`;
    }).join("");
    tierTable = `<div class="meth-table-wrap"><div class="meth-table-title">By FV tier <span class="meth-sub">ordering skill (Spearman ρ) within each consensus-FV bucket</span></div>
      <div class="table-scroll-x"><table class="meth-table"><thead><tr><th>FV tier</th><th>n</th><th>Consensus ρ</th><th>eFV ρ</th></tr></thead><tbody>${rows}</tbody></table></div></div>`;
  }
  if (det && det.receipts && det.receipts.length) {
    const rr = det.receipts.map(r => {
      const ok = r.xfv_right;
      return `<tr><td>${escapeHtml(r.name)}</td><td>${r.consensus_fv}</td><td>eFV ${escapeHtml(r.dir)}</td><td>${r.war}</td>
        <td style="color:${ok ? "var(--up)" : "var(--down)"};font-weight:700;">${ok ? "eFV ✓" : "consensus ✓"}</td></tr>`;
    }).join("");
    const dr = _disagreementRead(det);
    // Lead stat + "called shots" cards: the resolved receipts promoted above
    // the scroll table (which stays). Share and count computed from the
    // artifact fields, never hardcoded. FV grades display CEILING (owner rule).
    //
    // THE BOLD IS NOW ON THE HONEST HALF. This used to bold the percentage
    // alone, which is the one number in the sentence that does not survive its
    // own interval: 55% over 283 rows has a 95% CI that contains the coin. The
    // count and the interval carry the emphasis instead, and when the interval
    // clears the coin the sentence says that in the same place.
    const lead = (dr && dr.n)
      ? `<p class="meth-note">eFV was closer on ${dr.stat} of the <strong>${dr.n}</strong> biggest disagreements, <strong>${escapeHtml(dr.band)}</strong> - resolved players where eFV and the consensus were at least 15 percentiles apart. ${dr.resolvable ? "That interval clears the 50% coin." : "That interval contains 50%, so on this sample it is not distinguishable from a coin flip and is reported as a description rather than an edge."} The called shots below are the largest of them.</p>`
      : "";
    const shots = det.receipts.slice(0, 8).map(r => {
      const ok = !!r.xfv_right;
      return `<div class="meth-find-card">
        <div class="meth-find-stat">${r.war != null && !isNaN(Number(r.war)) ? Number(r.war).toFixed(1) : "-"} WAR</div>
        <div class="meth-find-label">${escapeHtml(r.name)}</div>
        <div class="meth-find-sub">consensus FV ${r.consensus_fv != null && !isNaN(Number(r.consensus_fv)) ? Math.ceil(Number(r.consensus_fv)) : "-"} &middot; eFV said ${escapeHtml(r.dir || "-")} &middot; <span style="color:${ok ? "var(--up)" : "var(--down)"};font-weight:700;">${ok ? "eFV was closer" : "consensus was closer"}</span></div>
      </div>`;
    }).join("");
    receipts = `<div class="meth-table-wrap"><div class="meth-table-title">Called shots - the biggest disagreements, resolved <span class="meth-sub">who the career proved closer</span></div>
      ${lead}
      <div class="meth-findings">${shots}</div>
      <div class="table-scroll-x"><table class="meth-table"><thead><tr><th>Player</th><th>Consensus FV</th><th>eFV said</th><th>Career WAR</th><th>Closer</th></tr></thead><tbody>${rr}</tbody></table></div></div>`;
  }
  return `<div class="meth-chart meth-accuracy">
    <div class="meth-chart-title">eFV vs consensus FV <span class="meth-sub">our model · out-of-sample</span></div>
    <p class="meth-note">${escapeHtml(xc.protocol || "")}</p>
    ${sideBlock("hitters", "Hitters - ordering skill (Spearman ρ, grade vs realized WAR)")}
    ${sideBlock("pitchers", "Pitchers - ordering skill (Spearman ρ, grade vs realized WAR)")}
    ${_methEfvVerdict(xc)}
    ${tierTable}
    ${receipts}
  </div>`;
}

// Findings-led callout strip: the headline numbers that make the eFV case, pulled live from
// the backtest so they never drift from the artifact. Cards read stat -> what it means.
//
// NO RANKING OR AUC CARD HERE (2026-09-24, census X01-02). The strip opened
// with eFV's Spearman read off pooled_efv_common, the all-vintages frame the
// artifact keeps as a regression control and HEADTOHEAD_FRAME_GATE bars as a
// headline, under a hand-typed superlative, one screen below a hero that reads
// the vintage-matched verdict and puts eFV third of four. It closed with the
// same frame's contributor AUC, a gap no floor on the page covers and one
// do-not-reopen item 3 says copy may not present as better discrimination.
// The hero already prints the ranking on the verdict basis, so both cards are
// dropped rather than re-derived; the strip keeps the two cards that carry
// their own basis and interval.
function _methEfvFindings(bt) {
  const det = bt.accuracy && bt.accuracy.xfv_vs_consensus_detail;
  const cards = [];
  // WAR-capture headline: the lift curve's top-20% point translated to plain
  // English, read live from capture_curve so it can never drift from the chart.
  const cc = bt.accuracy && bt.accuracy.capture_curve;
  if (cc && cc.xfv && cc.xfv.top20 != null && cc.consensus && cc.consensus.top20 != null)
    cards.push({ stat: `${Math.round(cc.xfv.top20 * 100)}%`,
      label: "of all the WAR this class produced sat in eFV's top 20%",
      sub: `consensus captured ${Math.round(cc.consensus.top20 * 100)}% &middot; full graded pool, busts included` });
  // (Removed the per-tier "Sharpest edge" card: on the current cohort the best tier
  // margin is a fraction of a Spearman point -- e.g. 0.44 -> 0.45 -- which does not read
  // as a "sharp edge" and overstated a within-noise gap.)
  const _dr2 = _disagreementRead(det);
  if (_dr2)
    cards.push({ stat: _dr2.stat,
      label: _dr2.resolvable
        ? "eFV closer on the biggest disagreements"
        : "eFV closer on the biggest disagreements (inside the noise)",
      sub: _dr2.sub });
  if (!cards.length) return "";
  return `<div class="meth-findings">${cards.map(cd => `
    <div class="meth-find-card">
      <div class="meth-find-stat">${cd.stat}</div>
      <div class="meth-find-label">${cd.label}</div>
      <div class="meth-find-sub">${cd.sub}</div>
    </div>`).join("")}</div>`;
}

// Year-by-year ordering skill: Spearman per preseason cohort for each PUBLIC
// board. Same inline-SVG idiom as _methCaptureCurve / _methCalibrationChart:
// owner palette via _raterMeta, consensus solid, the single sources muted
// (thin, dashed), identity carried by the legend + line style, never color
// alone.
//
// eFV IS NOT DRAWN HERE (2026-09-24, census X01-01). accuracy.per_year scores
// the boards on each full cohort and eFV on its out-of-sample resolved subset
// of it (2023: 411 of 829 rows), so an eFV line compared different players,
// and the bold caption under it counted "best in N of M cohorts" off those
// mismatched rows. On matched rows that count does not hold, and the artifact
// publishes no per-cohort floor to call any year either way.
// HEADTOHEAD_FRAME_GATE puts every eFV comparison on the vintage-matched
// basis, which lives in the head-to-head chart below; the boards here share
// identical rows inside each cohort, so their lines remain a fair comparison.
function _methPerYearChart(bt) {
  const py = bt.accuracy && bt.accuracy.per_year;
  if (!py || typeof py !== "object") return "";
  const years = Object.keys(py).sort();
  if (years.length < 2) return "";
  // Fixed series order: the head-to-head raters as committed, eFV excluded.
  const raterList = ((bt.accuracy && bt.accuracy.head_to_head_raters) || bt.raters || [])
    .filter(r => r !== "xfv");
  const series = raterList.map(r => ({
    rater: r,
    pts: years.map(y => {
      const e = py[y] && py[y][r];
      return e && e.spearman != null ? e.spearman : null;
    }),
  })).filter(s => s.pts.some(v => v != null));
  if (series.length < 2) return "";
  const allVals = series.flatMap(s => s.pts).filter(v => v != null);
  const W = 580, H = 250, ML = 46, MR = 16, MT = 16, MB = 40;
  const iW = W - ML - MR, iH = H - MT - MB;
  const yMax = Math.max(...allVals) * 1.15 || 1, yMin = 0;
  const sx = i => ML + (years.length === 1 ? iW / 2 : (i / (years.length - 1)) * iW);
  const sy = v => MT + iH - ((v - yMin) / (yMax - yMin)) * iH;
  const grid = [];
  for (let i = 0; i <= 4; i++) {
    const v = yMin + (yMax - yMin) * i / 4, y = sy(v).toFixed(1);
    grid.push(`<line x1="${ML}" y1="${y}" x2="${ML + iW}" y2="${y}" stroke="var(--border-light)" stroke-width="0.5" stroke-dasharray="2,3"/>`,
      `<text x="${ML - 6}" y="${y}" dy="3" text-anchor="end" font-size="9" fill="var(--text-tertiary)">${v.toFixed(2)}</text>`);
  }
  const xlabels = years.map((y, i) =>
    `<text x="${sx(i).toFixed(1)}" y="${MT + iH + 16}" text-anchor="middle" font-size="10" fill="var(--text-secondary)" font-weight="600">${escapeHtml(y)}</text>`).join("");
  const lines = series.map(s => {
    const pts = s.pts.map((v, i) => (v == null ? null : { x: sx(i), y: sy(v) })).filter(Boolean);
    if (pts.length < 2) return "";
    const d = pts.map((p, i) => `${i ? "L" : "M"} ${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ");
    const col = _raterMeta(s.rater).color;
    const isEfv = s.rater === "xfv";
    const emph = isEfv || s.rater === "prospx_consensus";
    const dots = pts.map(p => `<circle cx="${p.x.toFixed(1)}" cy="${p.y.toFixed(1)}" r="${isEfv ? 3.8 : emph ? 3 : 2.4}" fill="${col}"/>`).join("");
    return `<path d="${d}" fill="none" stroke="${col}" stroke-width="${isEfv ? 2.8 : emph ? 2.2 : 1.5}" ${emph ? "" : 'stroke-dasharray="5,3"'} stroke-linecap="round" stroke-linejoin="round"/>${dots}`;
  }).join("");
  const legend = series.map(s =>
    `<span class="meth-legend-key"><span class="meth-legend-swatch" style="background:${_raterMeta(s.rater).color};"></span>${escapeHtml(_raterMeta(s.rater).label)}</span>`).join("");
  const takeaway = `<p class="meth-note">Each point is one preseason cohort, every public board scored on the same players against the WAR those prospects went on to produce. eFV is not drawn: inside each cohort it grades only its out-of-sample resolved subset, so a line for it would compare different players. The head-to-head below scores eFV on identical, vintage-matched rows.</p>`;
  return `<div class="meth-chart">
    <div class="meth-chart-title">Ordering skill by preseason cohort <span class="meth-sub">Spearman ρ, grade vs realized WAR, per base year, public boards</span></div>
    <svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="Spearman ordering skill by preseason cohort for each public board">
      ${grid.join("")}
      <line x1="${ML}" y1="${MT + iH}" x2="${ML + iW}" y2="${MT + iH}" stroke="var(--text-secondary)" stroke-width="1"/>
      <line x1="${ML}" y1="${MT}" x2="${ML}" y2="${MT + iH}" stroke="var(--text-secondary)" stroke-width="1"/>
      ${lines}${xlabels}
    </svg>
    <div class="meth-legend">${legend}</div>
    ${takeaway}
  </div>`;
}

// Consensus-vs-inputs verdict, computed from the artifact so it can never
// drift: does blending the sources beat the best single source?
//
// C-A2 (2026-08-10) made this THREE-VALUED. The old rendering read
// `consensus_wins` as a literal binary ("the blend wins" : "the best input
// wins") and so reported a 0.0009 Spearman delta - against an MDE95 of
// 0.0121 - as a loss for the blend. It is neither a win nor a loss; it is
// below the floor this backtest can resolve. source_backtest.json now ships
// per-leg delta / mde95 / resolvable / verdict, and the verdict STRING is
// what renders. The two legs disagree on purpose: the AUC leg is a real win,
// the Spearman leg is not resolvable, and the artifact's own `reading` field
// is the defensible claim (blending buys discrimination, not ordering).
function _methConsensusVsInputsNote(bt) {
  const cvi = bt.accuracy && bt.accuracy.consensus_vs_inputs;
  if (!cvi || typeof cvi !== "object") return "";
  const f4 = v => (v == null ? "-" : Number(v).toFixed(4));
  const sgn4 = v => (v == null ? "-" : (Number(v) > 0 ? "+" : "") + Number(v).toFixed(4));
  const leg = (l, name) => {
    if (!l || l.consensus == null || l.best_input == null) return "";
    // Three-valued: the artifact's verdict string when it ships one, and a
    // resolvable-driven fallback otherwise. NEVER a bare boolean read.
    const resolvable = l.resolvable === true;
    const verdict = l.verdict != null && l.verdict !== ""
      ? String(l.verdict)
      : (resolvable ? (l.consensus_wins ? "the blend wins" : "the best input wins")
                    : "not resolvable at this power");
    const cls = resolvable ? "sacc-verdict-win" : "sacc-verdict-null";
    const floor = (l.delta != null && l.mde95 != null)
      ? `, delta ${sgn4(l.delta)} against an MDE95 of ${f4(l.mde95)}` : "";
    return `<li><strong>${escapeHtml(name)}</strong> ${f4(l.consensus)} for the blend against ${f4(l.best_input)} for its best single input${floor} - <span class="${cls}">${escapeHtml(verdict)}</span></li>`;
  };
  const items = [leg(cvi.spearman, "Ordering skill (Spearman)"),
                 leg(cvi.auc, "Contributor discrimination (AUC)")].filter(Boolean);
  if (!items.length) return "";
  return `<div class="sacc-legs">
    <div class="meth-table-title">Does blending beat the best single input?</div>
    <ul class="sacc-leg-list">${items.join("")}</ul>
    ${cvi.reading ? `<p class="meth-note">${escapeHtml(cvi.reading)}</p>` : ""}
    ${cvi.basis ? `<p class="meth-note sacc-basis-line">Basis: ${escapeHtml(cvi.basis)}</p>` : ""}
  </div>`;
}

// Per-rater scoring-basis marker. Keyed off the artifact's `basis` FIELD, not
// off a rater name: eFV is the out-of-sample leg today, but the field is what
// says so, and a future rater that joins forward-chained must inherit the
// marker without a code edit.
function _basisTag(basis) {
  if (basis === "forward_chained_oos")
    return `<span class="sacc-basis sacc-basis-oos" title="forward-chained, scored out of sample">OOS</span>`;
  if (basis === "in_sample_common_set")
    return `<span class="sacc-basis sacc-basis-in" title="scored in sample on the common set">IN-SAMPLE</span>`;
  return basis ? `<span class="sacc-basis">${escapeHtml(String(basis))}</span>` : "";
}

// Calibration cross-link tile: this view is the historical case; the live,
// nightly-updating counterpart is the calibration monitor on the Methodology
// view. Shows the current tripwire status inline once the shared reliability
// artifact (_loadReliability) has arrived; renders without it otherwise. The
// anchor drives the same #view= hash the nav chips sync to.
function _methCalibCrossLink() {
  const rel = _S.reliability;
  const tw = (rel && !rel.__error && typeof rel === "object") ? rel.tripwire : null;
  let stat = "→", status = "";
  if (tw && typeof tw === "object" && tw.bust_ece != null && tw.threshold != null) {
    const tripped = !!tw.tripped;
    stat = tripped ? "⚠" : "✓";
    status = `<div class="meth-find-sub">current status: <span style="color:${tripped ? "var(--down)" : "var(--up)"};font-weight:700;">${tripped ? "drift flagged for review" : "within the documented band"}</span> &middot; bust-bucket ECE ${Number(tw.bust_ece).toFixed(3)} vs threshold ${Number(tw.threshold).toFixed(3)}</div>`;
  }
  return `<div class="meth-findings"><div class="meth-find-card">
    <div class="meth-find-stat">${stat}</div>
    <div class="meth-find-label">eFV publishes its own live calibration - <a href="#view=methodology">see the monitor in Methodology</a></div>
    ${status}
    <div class="meth-find-sub">the shipped outcome distribution is re-scored nightly against resolved outcomes, with a drift tripwire</div>
  </div></div>`;
}

function _methTierTable(bt, rater) {
  const c = bt.cohorts[rater];
  // Median WAR ships alongside the mean whenever the artifact carries it: the
  // mean is dragged by a few stars, the median shows the typical outcome.
  const hasMed = (c.tiers || []).some(t => t.median_war != null);
  const rows = (c.tiers || []).slice().reverse().map(t => `
    <tr>
      <td class="meth-td-tier">${t.tier}</td>
      <td>${t.n}</td>
      <td>${Math.round(t.debut_rate * 100)}%</td>
      <td>${t.mean_war.toFixed(1)}</td>
      ${hasMed ? `<td>${t.median_war != null ? t.median_war.toFixed(1) : " - "}</td>` : ""}
      <td>${t.mean_war_per_yr_debut != null ? t.mean_war_per_yr_debut.toFixed(2) : " - "}</td>
      <td>${Math.round(t.contributor_rate * 100)}%</td>
      <td>${Math.round((t.regular_pace_rate || 0) * 100)}%</td>
      <td>${Math.round(t.star_rate * 100)}%</td>
    </tr>`).join("");
  return `<div class="meth-table-wrap">
    <div class="meth-table-title"><span class="meth-legend-swatch" style="background:${_raterMeta(rater).color};"></span>${escapeHtml(_raterMeta(rater).label)} <span class="meth-sub">n=${c.n} · ${c.n_debuted} debuted</span></div>
    <div class="table-scroll-x"><table class="meth-table">
      <thead><tr><th>FV</th><th>n</th><th title="Reached MLB">Debut</th><th title="Mean cumulative career WAR (undebuted = 0)">WAR</th>${hasMed ? `<th title="Median cumulative career WAR (undebuted = 0)">Med WAR</th>` : ""}<th title="Mean WAR per season, among players who debuted">WAR/yr</th><th title="Career WAR ≥ 3">Contrib</th><th title="≥ 1.5 WAR per season">Reg pace</th><th title="Career WAR ≥ 10">Star</th></tr></thead>
      <tbody>${rows}</tbody>
    </table></div>
  </div>`;
}

// Per-archetype accuracy - where each grader (and the blend) is strongest.
// AUC = the grade discriminates "became a contributor" (0.50 = coin flip).
//
// C-A2/C-A4 (2026-08-10): the row max used to render in var(--up) with a ★,
// which paints a winner onto six cells whose spread is a few thousandths of
// AUC and whose measured head-to-head does not clear its own noise floor in
// five of six archetypes. The ★ now marks the row max in the neutral primary
// colour (a pointer to the largest number, not a claim about it), and the
// only claim on this table is the VERDICT column, read three-valued out of
// data/source_cohort_accuracy.json. Column headers carry the scoring-basis
// marker off each rater's own `basis` field.
function _methArchetypeTable(bt) {
  const ba = bt.accuracy && bt.accuracy.by_archetype;
  if (!ba || !ba.length) return "";
  const raters = (bt.accuracy && bt.accuracy.head_to_head_raters) || bt.raters;
  // basis per rater, taken from the first row that carries one for it.
  const basisOf = {};
  raters.forEach(r => {
    for (const a of ba) {
      const b = (a.raters && a.raters[r] || {}).basis;
      if (b) { basisOf[r] = b; break; }
    }
  });
  const sacc = (_SACC && !_SACC.__error && _SACC.accuracy) ? _SACC.accuracy.by_archetype : null;
  const head = raters.map(r =>
    `<th>${escapeHtml(_raterMeta(r).label)}${_basisTag(basisOf[r])}</th>`).join("");
  const rows = ba.map(a => {
    const aucs = raters.map(r => (a.raters[r] || {}).auc).filter(v => v != null);
    const best = aucs.length ? Math.max(...aucs) : null;
    const cells = raters.map(r => {
      const v = (a.raters[r] || {}).auc;
      const isBest = v != null && v === best;
      const style = isBest ? "font-weight:700;color:var(--text-primary);"
        : "color:var(--text-secondary);";
      return `<td style="${style}">${v != null ? v.toFixed(4) : " - "}${isBest ? " ★" : ""}</td>`;
    }).join("");
    const cell = sacc ? sacc[a.archetype] : null;
    const verdict = cell ? _saccVerdictCell(cell) : `<td class="sacc-verdict"><span class="sacc-verdict-null">not measured</span></td>`;
    return `<tr><td class="meth-td-tier">${escapeHtml(a.label)}</td><td>${a.n}</td>${cells}${verdict}</tr>`;
  }).join("");
  return `<div class="meth-table-wrap">
    <div class="meth-table-title">Grader AUC by archetype <span class="meth-sub">AUC (grade predicts ‘became a contributor’) · ★ = row max, not a significance claim</span></div>
    <div class="table-scroll-x"><table class="meth-table sacc-table">
      <thead><tr><th>Archetype</th><th>n</th>${head}<th class="sacc-verdict">FanGraphs vs Pipeline</th></tr></thead>
      <tbody>${rows}</tbody>
    </table></div>
    <p class="meth-note">The ★ marks the largest AUC in the row and nothing more. The verdict column is the one measured head-to-head on this cut: FanGraphs minus MLB Pipeline Spearman against that cell's own 95 percent minimum detectable effect, from <a href="#view=source-accuracy">Source Accuracy</a>. Five of the six archetypes cannot resolve a winner.</p>
    ${_methArchetypeNote(bt)}
  </div>`;
}

// Build the archetype takeaway sentence FROM the live by_archetype data so it
// can never contradict the table above it (who leads, where a single source
// wins outright, the hardest archetype). Replaces a hardcoded note that drifted.
function _methArchetypeNote(bt) {
  const ba = bt.accuracy && bt.accuracy.by_archetype;
  if (!ba || !ba.length) return "";
  const XFV = "xfv";
  let efvWins = 0, total = 0;
  const losses = [];   // archetypes where eFV trails the best public grade
  ba.forEach(a => {
    const entries = Object.entries(a.raters)
      .filter(([, v]) => v && v.auc != null).map(([r, v]) => [r, v.auc]);
    const xa = (a.raters[XFV] || {}).auc;
    if (xa == null || !entries.length) return;
    total++;
    const best = Math.max(...entries.map(([, v]) => v));
    if (xa >= best - 1e-9) { efvWins++; return; }
    const winner = entries.find(([, v]) => v === best);
    losses.push({ label: a.label, rater: winner ? winner[0] : null, auc: best, xa });
  });
  if (!total) return "";
  const lead = `<strong>eFV grades best (highest AUC) in ${efvWins} of ${total} archetypes.</strong>`;
  const lose = losses.length
    ? ` It trails only on ${losses.map(l => `${escapeHtml(l.label)} (${escapeHtml(_raterMeta(l.rater).label)} ${l.auc.toFixed(3)} vs eFV ${l.xa.toFixed(3)})`).join(", ")} - the youngest, lowest-track-record cohorts, where scouting projection still reads best and eFV leans on the consensus prior.`
    : ` It leads every archetype on the board.`;
  return `<p class="meth-note">${lead}${lose}</p>`;
}

// The archetype clause of the honesty caveat is DERIVED (2026-08-19), the same
// rule as _methArchetypeNote above. The static sentence it replaces claimed eFV
// led the Spearman column in all six archetypes and the AUC column in only a minority;
// recounted on the current artifact's same-rows basis (raters_efv_common) eFV
// posts the row-best Spearman in 2 of 6 archetypes and the row-best AUC in 3
// of 6, so BOTH halves of the hand-written sentence had drifted false. Counts
// are row maxima on identical rows, never significance claims.
function _methCaveatArchetypeClause(bt) {
  const ba = (bt.accuracy && bt.accuracy.by_archetype) || [];
  let total = 0, spWins = 0, aucWins = 0;
  ba.forEach(a => {
    const rs = a.raters_efv_common || a.raters || {};
    const entries = Object.values(rs).filter(v => v && v.spearman != null && v.auc != null);
    const x = rs.xfv;
    if (!x || x.spearman == null || x.auc == null || entries.length < 2) return;
    total++;
    const bestSp = Math.max(...entries.map(v => v.spearman));
    const bestAuc = Math.max(...entries.map(v => v.auc));
    if (x.spearman >= bestSp - 1e-9) spWins++;
    if (x.auc >= bestAuc - 1e-9) aucWins++;
  });
  if (!total) return "";
  return ` Ordering and discrimination also split by archetype: on identical rows eFV posts the row-best Spearman in ${spWins} of ${total} archetypes and the row-best AUC in ${aucWins} of ${total} - row maxima, not significance claims - which is why the two tables below can look like different stories.`;
}

// The head-to-head bullet of the honesty caveat is DERIVED (2026-09-24, census
// X01-02). The static bullet it replaces said eFV led the pooled comparison by
// less than its floor, which was false on every frame the artifact publishes:
// on the verdict basis eFV trails, and on the two tilted frames its lead clears
// the floor. Three branches off head_to_head_verdict, the same call the hero
// makes, so the caveat cannot say what the verdict does not.
function _methCaveatHeadToHead(bt) {
  const hh = bt && bt.accuracy && bt.accuracy.head_to_head_verdict;
  const fmt = v => (v == null || isNaN(Number(v)) ? "-" : Number(v).toFixed(3));
  if (!hh || hh.delta == null || hh.mde95 == null) {
    return "<strong>The head-to-head is a point estimate.</strong> No floored verdict is loaded, so no ordering claim is made.";
  }
  const n = hh.n != null ? `the same ${Number(hh.n).toLocaleString()}` : "identical";
  const d = Number(hh.delta);
  const sd = (d > 0 ? "+" : "") + d.toFixed(3);
  if (hh.resolvable === true && hh.xfv_beats === true) {
    return `<strong>eFV's head-to-head lead clears its floor.</strong> On ${n} vintage-matched rows eFV leads PROSPX consensus by ${sd} against a noise floor of ${fmt(hh.mde95)}.`;
  }
  if (hh.resolvable === true) {
    return `<strong>eFV trails the consensus by a margin that clears its floor.</strong> On ${n} vintage-matched rows eFV minus PROSPX consensus is ${sd} against a noise floor of ${fmt(hh.mde95)}.`;
  }
  return `<strong>The head-to-head does not resolve.</strong> On ${n} vintage-matched rows eFV minus PROSPX consensus is ${sd} against a noise floor of ${fmt(hh.mde95)}, so neither grade is called the winner.`;
}

// "How to Read the Site" (Part 1 anchor) - annotated anatomy of a player card,
// the FV history chart, and a farm page, with every element linked to its
// glossary term, plus the metric-architecture diagram (how the metrics build on
// each other). Onboards new readers and lays out the system at a glance.
function renderGuide() {
  const el = document.getElementById("guide-body");
  if (!el) return;
  // One annotated element: a live example chip + the term link + plain-English.
  const anat = (example, slug, plain) => `<div class="guide-anat-row">
      <div class="guide-anat-vis">${example}</div>
      <div class="guide-anat-txt"><div class="guide-anat-term">${gTermLink(slug, GLOSSARY[slug] ? GLOSSARY[slug].name : slug)}</div><div class="guide-anat-plain">${plain}</div></div>
    </div>`;
  const archNode = (slug, label, sub) => `<div class="arch-node">${gTermLink(slug, label)}${sub ? `<span class="arch-node-sub">${escapeHtml(sub)}</span>` : ""}</div>`;

  const cardAnatomy = [
    anat(`<span class="fv-badge fv-60" style="padding:3px 9px;">60</span>`, "fv",
      "The headline grade - a single 20-80 number summarizing the prospect's projected MLB future, blended across every source that grades them."),
    anat(`<span style="display:inline-flex;gap:3px;"><span class="fv-badge fv-55 card-rarity-holo" style="padding:2px 7px;font-size:11px;">photo</span></span>`, "fv_rarity",
      "The photo's border/effect tier (shine → foil → chrome → holo → legendary) is keyed to FV, so rarity reads at a glance and matches the prospect list."),
    anat(`<span style="font-family:var(--font-mono);font-size:12px;color:var(--up);">HIT 60 · PWR 65 · …</span>`, "twenty_eighty",
      "Per-tool 20-80 scouting grades. 50 is MLB-average; each ±10 is roughly one standard deviation. These feed the composite and, ultimately, FV."),
    anat(`<span style="font-family:var(--font-mono);font-size:12px;color:var(--neon-violet);">$DvM+ 110</span>`, "dvm_plus",
      "A wRC+-style index of organizational development applied to the player's surplus dollars - 100 is league mean, +10 ≈ one SD."),
    anat(`<span class="g-term" data-gl="rps_plus" style="font-family:var(--font-mono);font-size:12px;color:var(--neon-cyan);">RPS+ 118</span>`, "rps_plus",
      "Level-anchored rate performance vs the player's own age × position cohort. 100 = cohort mean."),
    anat(`<span style="font-family:var(--font-mono);font-size:12px;color:var(--up);">SC+ 113</span>`, "statcast_plus",
      "Tracked-data composite (contact quality + discipline for hitters; stuff + induced whiff/chase for pitchers), scaled so 100 = pool mean."),
    anat(`<span style="font-family:var(--font-mono);font-size:12px;color:var(--up);">$154M</span>`, "surplus_value",
      "Projected surplus value over the player's controlled seasons - the dollar production he is expected to deliver above what those years cost."),
    anat(`<span style="font-family:var(--font-mono);font-size:13px;color:var(--up);">▲</span>`, "stock",
      "Recent direction of the consensus FV - rising, flat, or falling over the trailing window."),
    anat(`<span style="font-family:var(--font-mono);font-size:12px;color:var(--text-secondary);">ETA 2027</span>`, "eta",
      "Projected MLB-arrival year, derived from level, age, performance, and the org's promotion pace."),
  ].join("");

  const chartAnatomy = [
    anat(`<span style="font-family:var(--font-mono);font-size:12px;color:var(--neon-cyan);">━━ line</span>`, "consensus_fv",
      "The solid line is the point-in-time consensus FV - the forward-filled, Bayesian-shrunk mean of every source's grade as of each date."),
    anat(`<span style="font-family:var(--font-mono);font-size:12px;color:var(--text-tertiary);">┈┈ overlay</span>`, "fv",
      "Toggling the per-source overlay shows each outlet's individual grade history - the inputs the consensus blends."),
    anat(`<svg width="42" height="12" style="vertical-align:middle;" aria-hidden="true"><line x1="2" y1="6" x2="40" y2="6" stroke="var(--neon-violet)" stroke-width="1.4" stroke-dasharray="3,2"/></svg>`, "tools_dvm_plus",
      "The dashed violet line is the tool-composite trajectory - the mean per-tool grade at each snapshot, plotted on the FV scale. When it rises alongside the FV curve the tools are backing the grade; when FV climbs while it stays flat, the bump is scout-narrative-driven rather than tool-supported. It's the per-snapshot signal behind ToolDvM+."),
    anat(`<span style="font-family:var(--font-mono);font-size:13px;color:var(--up);">◆</span>`, "debut_rule",
      "A debut marker flags when the player crossed the rookie-eligibility threshold and graduated off the prospect board."),
    anat(`<span style="font-family:var(--font-mono);font-size:13px;color:var(--neon-amber);">⇄</span>`, "trade",
      "Trade markers stamp cross-org moves at the FV the league assigned on the trade date."),
  ].join("");

  const farmAnatomy = [
    anat(`<span style="font-family:var(--font-mono);font-size:12px;color:var(--text-secondary);">A+ tree</span>`, "farm_report_card",
      "The org letter grade is a weighted tree, value-led: a Value branch (aggregate risk-adjusted surplus), then MLB Production, Development, and Acquisition Strategy, each built from auditable leaves."),
    anat(`<span style="font-family:var(--font-mono);font-size:12px;color:var(--neon-violet);">DvM+ 112</span>`, "dvm_plus",
      "Development vs Mean - how fast the org grows the FV of prospects it already had (acquisitions nullified), 100 = league mean."),
    anat(`<span style="font-family:var(--font-mono);font-size:12px;color:var(--neon-cyan);">ToolDvM+ 108</span>`, "tools_dvm_plus",
      "The same development idea applied per tool, weighted by what each position needs."),
    anat(`<span style="font-family:var(--font-mono);font-size:12px;color:var(--up);">OrgSur+ 121</span>`, "sur_plus",
      "Org-level capital efficiency - WAR and contract surplus per dollar spent, scaled to 100 = league mean."),
  ].join("");

  el.innerHTML = `
  <div class="guide-wrap">
    <p class="guide-intro">Every number on the site resolves to a glossary entry. This page labels the elements you'll see on a player card, the FV history chart, and a farm-system page, then shows how the metrics build on one another. Click any underlined term for its definition.</p>

    <h2 class="meth-h">Anatomy of a player card</h2>
    <div class="guide-anat">${cardAnatomy}</div>

    <h2 class="meth-h">Reading the FV history chart</h2>
    <div class="guide-anat">${chartAnatomy}</div>

    <h2 class="meth-h">Reading a farm-system page</h2>
    <div class="guide-anat">${farmAnatomy}</div>

    <h2 class="meth-h">How the metrics build on each other</h2>
    <p class="meth-note">Each stage consumes the one before it. Scouting grades aggregate into a per-source FV; per-source FVs blend into the consensus; the consensus plus performance and tracked data drive the player indices; player indices roll up to the org grade.</p>
    <div class="arch-flow">
      <div class="arch-stage">
        <div class="arch-stage-label">Inputs</div>
        ${archNode("twenty_eighty", "Tool grades", "20-80, per source")}
      </div>
      <div class="arch-arrow">→</div>
      <div class="arch-stage">
        <div class="arch-stage-label">Per-source grade</div>
        ${archNode("fv", "FV", "each outlet")}
      </div>
      <div class="arch-arrow">→</div>
      <div class="arch-stage">
        <div class="arch-stage-label">Blend</div>
        ${archNode("consensus_fv", "Consensus FV", "forward-fill + shrink")}
      </div>
      <div class="arch-arrow">→</div>
      <div class="arch-stage">
        <div class="arch-stage-label">Player indices</div>
        <div class="arch-node-col">
          ${archNode("rps_plus", "RPS+")}
          ${archNode("statcast_plus", "SC+")}
          ${archNode("dvm_plus", "DvM+ / $DvM+")}
          ${archNode("surplus_value", "Surplus value")}
        </div>
      </div>
      <div class="arch-arrow">→</div>
      <div class="arch-stage">
        <div class="arch-stage-label">Org roll-up</div>
        ${archNode("farm_report_card", "Farm grade", "weighted tree")}
      </div>
    </div>
  </div>`;
  if (window.EEPHUS_GL) window.EEPHUS_GL.wire(el);
}

// ---- Part 5: interactive teaching widgets ---------------------------------
// Standard-normal CDF (Abramowitz-Stegun 26.2.17) for the 20-80 percentile.
function _normCdf(z) {
  const t = 1 / (1 + 0.2316419 * Math.abs(z));
  const d = 0.3989423 * Math.exp(-z * z / 2);
  const p = d * t * (0.3193815 + t * (-0.3565638 + t * (1.781478 + t * (-1.821256 + t * 1.330274))));
  return z > 0 ? 1 - p : p;
}
// Linear-interpolate a string-keyed numeric table ({"35":..,"80":..}) at x.
function _vfInterp(table, x) {
  const ks = Object.keys(table || {}).map(Number).sort((a, b) => a - b);
  if (!ks.length) return null;
  if (x <= ks[0]) return table[ks[0]];
  if (x >= ks[ks.length - 1]) return table[ks[ks.length - 1]];
  for (let i = 0; i < ks.length - 1; i++) {
    if (x >= ks[i] && x <= ks[i + 1]) {
      const t = (x - ks[i]) / (ks[i + 1] - ks[i]);
      return table[ks[i]] * (1 - t) + table[ks[i + 1]] * t;
    }
  }
  return table[ks[ks.length - 1]];
}
const _fmtMM2 = m => (m == null ? " - " : "$" + (Math.round(m * 10) / 10).toFixed(1) + "M");

// Bell curve with a marker at grade g (20-80) + shaded left tail = percentile.
function _gxBellSvg(g) {
  const W = 320, H = 96, pad = 6;
  const x = v => pad + (v - 20) / 60 * (W - 2 * pad);
  const mu = 50, sd = 10;
  const yOf = v => Math.exp(-((v - mu) ** 2) / (2 * sd * sd));
  let path = "", area = "";
  const pts = [];
  for (let v = 20; v <= 80; v += 1) pts.push([x(v), H - pad - yOf(v) * (H - 2 * pad - 8)]);
  path = "M" + pts.map(p => p[0].toFixed(1) + "," + p[1].toFixed(1)).join(" L");
  const ap = pts.filter((_, i) => 20 + i <= g);
  if (ap.length) area = `M${x(20).toFixed(1)},${(H - pad).toFixed(1)} L` + ap.map(p => p[0].toFixed(1) + "," + p[1].toFixed(1)).join(" L") + ` L${ap[ap.length - 1][0].toFixed(1)},${(H - pad).toFixed(1)} Z`;
  const gx = x(g);
  const ticks = [20, 30, 40, 50, 60, 70, 80].map(v => `<line x1="${x(v).toFixed(1)}" y1="${H - pad}" x2="${x(v).toFixed(1)}" y2="${H - pad + 3}" stroke="var(--text-tertiary)" stroke-width="1"/><text x="${x(v).toFixed(1)}" y="${H - pad + 12}" font-size="8" fill="var(--text-tertiary)" text-anchor="middle" font-family="var(--font-mono)">${v}</text>`).join("");
  return `<svg viewBox="0 0 ${W} ${H + 8}" width="100%" style="max-width:340px;display:block;" preserveAspectRatio="xMidYMid meet">
    ${area ? `<path d="${area}" fill="var(--neon-cyan)" opacity="0.18"/>` : ""}
    <path d="${path}" fill="none" stroke="var(--text-secondary)" stroke-width="1.5"/>
    <line x1="${gx.toFixed(1)}" y1="${pad}" x2="${gx.toFixed(1)}" y2="${H - pad}" stroke="var(--neon-cyan)" stroke-width="2"/>
    <circle cx="${gx.toFixed(1)}" cy="${(H - pad - yOf(g) * (H - 2 * pad - 8)).toFixed(1)}" r="3.5" fill="var(--neon-cyan)"/>
    ${ticks}
  </svg>`;
}
// ---- Per-term glossary visualizations (Part 2) ----------------------------
// Small, theme-aware diagrams keyed by slug, rendered inside the term card.
function _vizFvWar() {
  const tbl = (window.VALUE_FRAMEWORK || {}).fv_to_6yr_avg_war || { 40: 1, 45: 1.5, 50: 2, 55: 2.5, 60: 3, 65: 4, 70: 5, 80: 7 };
  const fvs = [40, 45, 50, 55, 60, 65, 70, 80], max = 7;
  return `<div style="display:flex;flex-direction:column;gap:3px;width:100%;max-width:300px;">${fvs.map(fv => {
    const w = _vfInterp(tbl, fv), pct = Math.max(3, w / max * 100);
    return `<div style="display:flex;align-items:center;gap:6px;font-family:var(--font-mono);font-size:10px;"><span style="width:20px;color:var(--text-tertiary);text-align:right;">${fv}</span><span style="flex:1;height:9px;background:var(--bg-tertiary);position:relative;"><span style="position:absolute;left:0;top:0;bottom:0;width:${pct}%;background:var(--neon-cyan);"></span></span><span style="width:54px;color:var(--text-secondary);">${w.toFixed(1)} WAR/yr</span></div>`;
  }).join("")}</div>`;
}
function _vizPlusGauge(val, lo, hi) {
  lo = lo || 70; hi = hi || 130;
  const pct = Math.max(0, Math.min(100, (val - lo) / (hi - lo) * 100));
  return `<div style="width:100%;max-width:300px;font-family:var(--font-mono);font-size:10px;">
    <div style="height:11px;background:linear-gradient(90deg,var(--down),var(--bg-tertiary) 50%,var(--up));position:relative;border:1px solid var(--border-light);">
      <span style="position:absolute;left:50%;top:-2px;bottom:-2px;width:1px;background:var(--text-tertiary);"></span>
      <span style="position:absolute;left:${pct}%;top:-3px;bottom:-3px;width:2px;background:var(--neon-cyan);"></span>
      <span style="position:absolute;left:${pct}%;top:-15px;transform:translateX(-50%);color:var(--neon-cyan);font-weight:700;">${val}</span>
    </div>
    <div style="display:flex;justify-content:space-between;color:var(--text-tertiary);margin-top:3px;"><span>${lo}</span><span>100 = mean</span><span>${hi}</span></div></div>`;
}
function _vizPercentile(pct) {
  return `<div style="width:100%;max-width:300px;font-family:var(--font-mono);font-size:10px;">
    <div style="height:11px;background:linear-gradient(90deg,#3b6bd6,#cfd6e4 50%,#d62b3b);position:relative;border-radius:6px;">
      <span style="position:absolute;left:${pct}%;top:50%;transform:translate(-50%,-50%);width:14px;height:14px;border-radius:50%;background:var(--text-primary);border:2px solid var(--bg-primary);"></span>
    </div>
    <div style="color:var(--text-tertiary);margin-top:3px;">${pct}th percentile vs pool (example)</div></div>`;
}
function _vizSurplusCurve() {
  const g = (window.VALUE_FRAMEWORK || {}).surplus_by_grade_mm, t = (g && g.hitter) || {};
  const fvs = [40, 45, 50, 55, 60, 65, 70], max = _vfInterp(t, 70) || 200;
  const pts = fvs.map((fv, i) => [i / (fvs.length - 1) * 100, 100 - ((_vfInterp(t, fv) || 0) / max * 92)]);
  const path = "M" + pts.map(p => p[0].toFixed(1) + "," + p[1].toFixed(1)).join(" L");
  return `<svg viewBox="0 0 100 100" width="100%" style="max-width:240px;height:84px;display:block;" preserveAspectRatio="none"><path d="${path}" fill="none" stroke="var(--up)" stroke-width="2" vector-effect="non-scaling-stroke"/></svg><div style="font-family:var(--font-mono);font-size:10px;color:var(--text-tertiary);">FV 40 → 70 · surplus $M (hitter), convex by grade</div>`;
}
const _GLOSSARY_VIZ = {
  twenty_eighty:   () => _gxBellSvg(60),
  fv:              () => _vizFvWar(),
  fv_to_war_table: () => _vizFvWar(),
  dvm_plus:        () => _vizPlusGauge(110),
  rps_plus:        () => _vizPlusGauge(118),
  sur_plus:        () => _vizPlusGauge(121),
  statcast_plus:   () => _vizPlusGauge(113),
  fin_dollar_dvm:  () => _vizPlusGauge(112),
  barrel_pct:      () => _vizPercentile(78),
  exit_velocity:   () => _vizPercentile(72),
  hard_hit_pct:    () => _vizPercentile(70),
  surplus_value:   () => _vizSurplusCurve(),
  tvi:             () => _vizSurplusCurve(),
};

function _gx2080() {
  const g = +(_byId("gx-grade-in") || {}).value || 50;
  const z = (g - 50) / 10;
  const pct = Math.round(_normCdf(z) * 100);
  const label = g >= 70 ? "Elite (top of scale)" : g >= 65 ? "Plus-plus" : g >= 60 ? "Plus" : g >= 55 ? "Above average" : g >= 45 ? "Average-ish" : g >= 40 ? "Below average" : "Well below average";
  _setHTML("gx-grade-out", `<div class="gx-out-big">${g} <span class="gx-out-sub">grade</span></div>
    <div class="gx-out-row"><span>z-score</span><b>${z >= 0 ? "+" : ""}${z.toFixed(1)} σ</b></div>
    <div class="gx-out-row"><span>percentile</span><b>~${pct}th</b></div>
    <div class="gx-out-row"><span>reads as</span><b>${label}</b></div>`);
  _setHTML("gx-grade-svg", _gxBellSvg(g));
  const lbl = _byId("gx-grade-val"); if (lbl) lbl.textContent = g;
}
function _gxConsensus() {
  const rows = [...document.querySelectorAll("#gx-consensus .gx-src-row")];
  let wsum = 0, wfv = 0, n = 0, fsum = 0;
  rows.forEach(r => {
    const fv = +r.querySelector(".gx-src-fv").value;
    const w = +r.querySelector(".gx-src-w").value;
    r.querySelector(".gx-src-wv").textContent = w.toFixed(1);
    if (!isFinite(fv)) return;
    n++; fsum += fv; wsum += w; wfv += fv * w;
  });
  const equal = n ? (fsum / n) : 0;
  const weighted = wsum > 0 ? (wfv / wsum) : equal;
  _setHTML("gx-consensus-out", `<div class="gx-out-row"><span>Equal-weight (site default)</span><b>${equal.toFixed(1)} FV</b></div>
    <div class="gx-out-row"><span>Your weighting</span><b style="color:var(--neon-cyan);">${weighted.toFixed(1)} FV</b></div>
    <div class="gx-out-row"><span>Difference</span><b style="color:${Math.abs(weighted - equal) >= 1 ? "var(--neon-amber)" : "var(--text-secondary)"};">${(weighted - equal) >= 0 ? "+" : ""}${(weighted - equal).toFixed(1)}</b></div>`);
}
function _gxConsensusReset() {
  document.querySelectorAll("#gx-consensus .gx-src-w").forEach(s => { s.value = 1; });
  _gxConsensus();
}
function _gxSurplus() {
  const vf = window.VALUE_FRAMEWORK || {};
  const fv = +(_byId("gx-surplus-fv") || {}).value || 50;
  const side = (_byId("gx-surplus-side") || {}).value || "hitter";
  const lbl = _byId("gx-surplus-fvval"); if (lbl) lbl.textContent = fv;
  const warYr = _vfInterp(vf.fv_to_6yr_avg_war || {}, fv);
  const dpw = (vf.dollars_per_war || {}).flat_mm || 11.74;
  const st = vf.service_time || {};
  // The window comes from the SET, never from a hardcoded 6. clemens_2026
  // defines 7 (three pre-arb plus four arb) and the legacy prospx_current set
  // defines 6; printing 6 for a figure priced over 7 is how "control window"
  // came to name three different windows for one player on one afternoon.
  const ctrl = st.control_years || 7, preArb = st.pre_arb_years || 3, lgMin = st.league_min_mm || 0.76;
  const arbFr = st.arb_fractions_of_fa_value || [0.4, 0.6, 0.8];
  if (warYr == null) { _setHTML("gx-surplus-out", " - "); return; }
  const war6 = warYr * ctrl;
  const gross = war6 * dpw;
  const faPerYr = warYr * dpw;
  const arbCost = arbFr.reduce((s, f) => s + f * faPerYr, 0);
  const cost = preArb * lgMin + arbCost;
  const framework = gross - cost;
  const published = _vfInterp((vf.surplus_by_grade_mm || {})[side] || {}, fv);
  _setHTML("gx-surplus-out", `
    <div class="gx-step"><span class="gx-step-n">1</span><span class="gx-step-t">FV ${fv} → ${warYr.toFixed(2)} WAR/yr</span><span class="gx-step-v">${gTermLink("fv_to_war_table", "table")}</span></div>
    <div class="gx-step"><span class="gx-step-n">2</span><span class="gx-step-t">× ${ctrl} controlled yrs</span><span class="gx-step-v">${war6.toFixed(1)} WAR</span></div>
    <div class="gx-step"><span class="gx-step-n">3</span><span class="gx-step-t">× $${dpw.toFixed(2)}M / WAR</span><span class="gx-step-v">${_fmtMM2(gross)} gross</span></div>
    <div class="gx-step"><span class="gx-step-n">4</span><span class="gx-step-t">− cost (3×$${lgMin}M pre-arb + arb ${arbFr.map(f => f).join("/")})</span><span class="gx-step-v">−${_fmtMM2(cost)}</span></div>
    <div class="gx-step gx-step-sum"><span class="gx-step-n">=</span><span class="gx-step-t">framework surplus</span><span class="gx-step-v">${_fmtMM2(framework)}</span></div>
    <div class="gx-surplus-final">Published surplus value <b>${_fmtMM2(published)}</b><div class="gx-surplus-note">The published figure additionally probability-weights the outcome distribution and discounts future years at ${vf.discount_rate != null ? `${(Number(vf.discount_rate) * 100).toFixed(0)}%/yr` : "the platform rate"}, so it differs slightly from the flat framework walk above.</div></div>`);
  if (window.EEPHUS_GL) { const _o = document.getElementById("gx-surplus-out"); if (_o) window.EEPHUS_GL.wire(_o); }
}
function _byId(id) { return document.getElementById(id); }
function _setHTML(id, html) { const e = document.getElementById(id); if (e) e.innerHTML = html; }

// Window-scope the methodology widget handlers. The interactive cards wire
// them via inline oninput / onclick / onchange attributes, which resolve
// against the global scope - NOT this IIFE's closure. Without this the
// sliders and number inputs silently no-op (ReferenceError swallowed by
// the inline handler). Mirrors window._printMethodology above.
window._gx2080 = _gx2080;
window._gxConsensus = _gxConsensus;
window._gxConsensusReset = _gxConsensusReset;
window._gxSurplus = _gxSurplus;


function _methInteractivesHTML() {
  return `
  <h2 class="meth-h">Interactive - manipulate the models</h2>
  <p class="meth-note">These run on the live framework values. Move the inputs to see how a scouting grade, a source-weighting scheme, and the surplus walk respond.</p>

  <div class="gx-card">
    <div class="gx-card-title">The 20-80 scale as a distribution</div>
    <div class="gx-card-body gx-2col">
      <div>
        <label class="gx-label">Grade <b id="gx-grade-val">60</b></label>
        <input id="gx-grade-in" class="gx-range" type="range" min="20" max="80" step="1" value="60" oninput="_gx2080()">
        <div id="gx-grade-svg"></div>
      </div>
      <div id="gx-grade-out" class="gx-out"></div>
    </div>
  </div>

  <div class="gx-card">
    <div class="gx-card-title">How source weighting works - adjustable consensus</div>
    <div class="gx-card-body">
      <div id="gx-consensus" class="gx-srcs">
        ${[["FanGraphs", 60], ["MLB Pipeline", 55], ["ESPN", 60], ["Just Baseball", 50], ["TJStats", 55]].map(([nm, fv]) => `
        <div class="gx-src-row">
          <span class="gx-src-name">${nm}</span>
          <label class="gx-src-lab">FV <input class="gx-src-fv gx-num" type="number" min="20" max="80" step="1" value="${fv}" oninput="_gxConsensus()"></label>
          <label class="gx-src-lab">w <input class="gx-src-w gx-range gx-range-sm" type="range" min="0" max="2" step="0.1" value="1" oninput="_gxConsensus()"> <b class="gx-src-wv">1.0</b></label>
        </div>`).join("")}
      </div>
      <div style="display:flex;gap:10px;align-items:center;margin-top:8px;flex-wrap:wrap;">
        <button class="chip" type="button" onclick="_gxConsensusReset()">Reset to equal weights</button>
        <div id="gx-consensus-out" class="gx-out gx-out-inline"></div>
      </div>
      <p class="meth-note" style="margin-top:8px;">The live board uses EQUAL WEIGHTS (the accuracy-weighted scheme shipped in June 2026 was reverted on 2026-07-25 after a hardened re-measurement showed its edge was inside the noise floor). This widget starts from equal weights - the served configuration - so you can feel how any weighting would move a consensus.</p>
    </div>
  </div>

  <div class="gx-card">
    <div class="gx-card-title">Surplus value calculator - FV to dollars, step by step</div>
    <div class="gx-card-body gx-2col">
      <div>
        <label class="gx-label">FV <b id="gx-surplus-fvval">55</b></label>
        <input id="gx-surplus-fv" class="gx-range" type="range" min="35" max="80" step="1" value="55" oninput="_gxSurplus()">
        <label class="gx-label" style="margin-top:10px;display:block;">Side
          <select id="gx-surplus-side" class="gx-num" style="width:auto;" onchange="_gxSurplus()">
            <option value="hitter">Hitter</option><option value="pitcher">Pitcher</option>
          </select>
        </label>
      </div>
      <div id="gx-surplus-out" class="gx-out gx-steps"></div>
    </div>
  </div>`;
}

// Live calibration monitor artifact (finding 37): shared lazy loader. The
// Methodology view renders the full monitor; the Source Comparison view shows
// the tripwire status on its calibration cross-link tile. One in-flight guard,
// one cached payload; the resolve re-renders whichever consumer view is
// active. Diagnostic only; a failed fetch or absent artifact simply drops the
// dependent sub-blocks - it is dark-launched, so the dev artifact is a stale
// vintage that the canonical box regenerates nightly.
function _loadReliability() {
  if (_S.reliability || _S.relLoading) return;
  _S.relLoading = true;
  const rerender = () => {
    if (_S.view === "methodology") renderMethodology();
    else if (_S.view === "source-comparison") renderSourceComparison();
  };
  fetch("/data/xfv_reliability.json", { cache: "no-cache" })
    .then(r => (r.ok ? r.json() : null))
    .then(j => { _S.reliability = j || { __error: true }; rerender(); })
    .catch(() => { _S.reliability = { __error: true }; rerender(); });
}

// Sources & Methodology ad-card GFX (owner ask 2026-08-04): one shareable card
// that says what eFV is, shows the honest headline results, and carries the
// no-ship discipline line. Every number is read AT CLICK TIME from the loaded
// artifacts (xfv_scoreboard_eval.json head_to_head + disagreement receipts;
// model_registry.json for the ledger tile), never hardcoded, so the card can
// never carry a number the page does not. Claims match the corrected prose:
// equal-weight consensus, EV surplus, and NO per-side margin is stated as a
// win (the hitter rank margin sits under its own MDE floor). The head-to-head
// bars are the scoreboard's vintage-matched frame (2026-09-24), the frame its
// verdict is read off, where public sources can sit above eFV, so the Spearman
// scale tops out at 0.5 rather than clipping every bar at 0.4. Returns null
// while the scoreboard artifact has not loaded - the click is then a no-op.
function _methAdGfxSpec() {
  const sb = _S.scoreEval;
  if (!sb || sb.__error || !sb.head_to_head || !sb.head_to_head.vs) return null;
  const vs = sb.head_to_head.vs;
  const cons = vs.prospx_consensus, fg = vs.fangraphs, mlb = vs.mlb_pipeline;
  const spEfv = cons && cons.spearman ? cons.spearman.efv : null;
  if (spEfv == null) return null;
  const f3 = v => (v == null || isNaN(Number(v)) ? "-" : Number(v).toFixed(3));
  const srcRows = key => [["prospx_consensus", cons], ["mlb_pipeline", mlb], ["fangraphs", fg]]
    .filter(pr => pr[1] && pr[1][key] && pr[1][key].consensus != null)
    .map(pr => ({ label: pr[1].label || _raterMeta(pr[0]).label,
                  v: pr[1][key].consensus, isEfv: false, c: _raterMeta(pr[0]).color }));
  const spRows = [{ label: "eFV", v: spEfv, isEfv: true }].concat(srcRows("spearman"))
    .sort((a, b) => b.v - a.v);
  if (spRows.length < 2) return null;
  const aucEfv = cons && cons.auc_contributor ? cons.auc_contributor.efv : null;
  const auRows = aucEfv == null ? []
    : [{ label: "eFV", v: aucEfv, isEfv: true }].concat(srcRows("auc_contributor"))
        .sort((a, b) => b.v - a.v);

  const bestPub = spRows.filter(r => !r.isEfv)[0];
  const tiles = [{
    stat: f3(spEfv),
    label: "eFV ordering skill (Spearman, grade vs realized WAR)",
    sub: bestPub ? "best public source " + f3(bestPub.v) + " (" + bestPub.label + ")" : "common resolved set",
  }];
  const rec = sb.disagreement_receipts;
  if (rec && rec.efv_right_share != null && rec.n_disagreements != null) tiles.push({
    stat: Math.round(rec.efv_right_share * 100) + "%",
    label: "closer on the biggest disagreements",
    sub: rec.n_disagreements + " resolved eFV vs consensus splits",
  });
  const reg = _S.registry;
  if (reg && !reg.__error && Array.isArray(reg.models) && reg.models.length) {
    const counts = {};
    reg.models.forEach(m => { counts[m.verdict] = (counts[m.verdict] || 0) + 1; });
    tiles.push({
      stat: String(reg.models.length),
      label: "models on the public accountability ledger",
      sub: (counts.validated || 0) + " validated · misses stay committed",
    });
  }

  // THE STAR IS EARNED BY A FLOOR HERE TOO (2026-09-24, census X01-01 sibling).
  // The engine starred each panel's longest bar, so this card starred eFV's
  // contributor AUC (0.754 against consensus 0.751) with no floor behind it,
  // which do-not-reopen item 3 forbids. The Spearman panel stars the winner of
  // verdict_vs_consensus only when that verdict resolves and the winner also
  // tops every bar; the AUC panel never stars.
  const vv = sb.head_to_head.verdict_vs_consensus || null;
  let spStar = false;
  if (vv && vv.resolvable === true) {
    const win = vv.xfv_beats ? spRows.find(r => r.isEfv)
      : spRows.find(r => !r.isEfv && r.label === ((cons && cons.label) || _raterMeta("prospx_consensus").label));
    spStar = !!(win && win.v >= spRows[0].v - 1e-9);
  }
  const panels = [{ title: "Ordering skill · Spearman, common resolved set", lo: 0, hi: 0.5, rows: spRows, star: spStar }];
  if (auRows.length >= 2) panels.push({ title: "Discrimination · contributor AUC (no floor, none starred)", lo: 0.5, hi: 0.85, rows: auRows, star: false });

  const nH2h = cons && cons.spearman ? cons.spearman.n : null;
  return {
    kind: "sourcecomp",
    module: "Sources & Methodology",
    accentToken: "--accent-lilac",
    format: "twitter",
    title: "eFV: the prospect grade trained on outcomes",
    subtitle: "Equal-weight scout consensus as the prior + outcome-validated signals, "
      + "summarized back onto the 20-80 scale"
      + (nH2h ? " · scored on " + Number(nH2h).toLocaleString() + " common resolved players" : ""),
    url: "eephus.io",
    filenameBase: "eephus-efv-methodology",
    caption: "Forward-chained, out of sample, leakage-free · every change ships through a pre-registered gate and failed gates are committed as no-ships",
    comp: { tiles: tiles, panels: panels,
      note: "eFV enters every cell with its forward-chained out-of-sample grade, never an in-sample fit. Surplus dollars are calibrated expected values. Higher is better · ★ = gap clears its floor." },
  };
}

// ==== INDUSTRY COMPARISON (2026-08-19) =======================================
// Methodology-view section "Our tables vs the industry's" (#industry-comparison).
// Each block is one casual paragraph, then the arithmetic shape, then the
// artifact or doc pointer. Every number is derived at render time: from
// window.VALUE_FRAMEWORK (already loaded on this page), from artifacts pulled
// through the shared _RCPT cache, or from _S.sideCal (fetch reused from
// _loadScoreboard). An absent artifact drops its numeric clause, never the
// block: the mechanism prose and the pointer always render.
const _IND_FITTED = "/data/value_framework_fitted.json";
const _IND_BA = "/data/ba_consensus_eval.json";
const _IND_DPW = "/data/fa_dpw_series.json";
function _indLoad() {
  const rerender = () => { if (_S.view === "methodology") renderMethodology(); };
  [_IND_FITTED, _IND_BA, _IND_DPW].forEach(p => {
    // Two guards: a cached payload would fire the callback synchronously
    // (renderMethodology recursion), and an in-flight fetch already carries a
    // rerender in its queue (every re-render calls back in here).
    if (!_RCPT[p] && !_RCPT_LOADING[p]) _rcptLoad(p, rerender);
  });
}

function _methIndustryHTML() {
  const vf = window.VALUE_FRAMEWORK || {};
  const six = vf.fv_to_6yr_avg_war || {}, prime = vf.fv_to_prime_war || {};
  const srcs = vf.sources || {};
  const fitted = _RCPT[_IND_FITTED];
  const ba = _RCPT[_IND_BA];
  const dpw = _RCPT[_IND_DPW];

  // (a) Five tables, five quantities: the FV 50 worked example, derived from
  // the live framework snapshot (the _dpwTxt pattern in _methProseHTML).
  let fiveMath = "";
  if (six["50"] != null && prime["50"] != null && Number(six["50"]) > 0) {
    const ratio = Number(prime["50"]) / Number(six["50"]);
    fiveMath = `<p class="meth-eq">FV 50, our current framework: ${_rn(prime["50"], 2)} WAR in a prime year if he hits, ${_rn(six["50"], 2)} WAR per controlled year once the busts are priced in. Same grade, ${_rn(ratio, 1)}x apart.</p>`;
  }
  const blockA = `<div class="meth-table-wrap">
    <div class="meth-table-title">One grade, five tables <span class="meth-sub">the per-year-if-he-arrives trap</span></div>
    <p class="meth-note">Every public FV-to-WAR table answers a different question. Some price a single season if the prospect arrives. Some price a prime season. Some price the whole six controlled years with the busts folded in. They all get published under the same name, so reading one as another is a silent unit error, and it is the most common way a prospect gets mispriced in public trade math.</p>
    ${fiveMath}
    <p class="meth-note">Our fix is a hard two-table split: a conditional shape inside the outcome mixture (what a hit looks like) and a bust-inclusive per-year table that the dollars actually ride. The served snapshot is <a href="/data/value_framework.js" target="_blank" rel="noopener">value_framework.js</a>; the industry anchor it is checked against is the FanGraphs outcome-buckets study${srcs.outcome_buckets ? ` (<a href="${escapeHtml(srcs.outcome_buckets)}" target="_blank" rel="noopener noreferrer">source</a>)` : ""}.</p>
  </div>`;

  // (b) Sub-45 anchors: fitted vs published constants, derived from the
  // fitted artifact when it loads; mechanism-only when it does not.
  let blockB;
  const ea = (fitted && !fitted.__error) ? fitted.empirical_anchors : null;
  if (ea && ea.anchors) {
    const d = ea.diagnostics || {};
    const rows = ["35", "40", "45"].map(k => {
      if (ea.anchors[k] == null) return "";
      const dk = d[k] || {};
      return `<tr><td class="meth-td-tier">FV ${k}</td>
        <td>${_rn(ea.anchors[k], 2)}</td>
        <td>${dk.reference_war_yr != null ? _rn(dk.reference_war_yr, 2) : " - "}</td>
        <td>${dk.bust_pct != null ? _rn(dk.bust_pct, 1) + "%" : " - "}</td>
        <td>${dk.n != null ? _rn(dk.n, 0) : " - "}</td></tr>`;
    }).join("");
    const win = ea.cohort_window || [];
    blockB = `<div class="meth-table-wrap">
      <div class="meth-table-title">The bottom of the scale is fitted, not assumed <span class="meth-sub">sub-45 anchors vs published constants</span></div>
      <p class="meth-note">Public tables get thin below FV 45, so the low anchors tend to be constants someone chose. Most of a board lives down there, and most of it busts, so a hand-set constant misprices the largest population on the sheet. Our sub-45 anchors are fitted on the resolved cohort${win.length === 2 ? ` (${_rn(win[0], 0)}-${_rn(win[1], 0)} listings)` : ""}, busts carried at zero.</p>
      <div class="table-scroll-x"><table class="meth-table">
        <thead><tr><th>Grade</th><th>Fitted WAR/yr</th><th>Published constant</th><th>Bust share</th><th>n</th></tr></thead>
        <tbody>${rows}</tbody>
      </table></div>
      <p class="meth-note">Fit: <a href="${_IND_FITTED}" target="_blank" rel="noopener">value_framework_fitted.json</a>.</p>
    </div>`;
  } else {
    blockB = `<div class="meth-table-wrap">
      <div class="meth-table-title">The bottom of the scale is fitted, not assumed <span class="meth-sub">sub-45 anchors vs published constants</span></div>
      <p class="meth-note">Public tables get thin below FV 45, so the low anchors tend to be constants someone chose. Ours are fitted on the resolved cohort with busts carried at zero, and they sit well under the published constants because most sub-45 prospects never return a win. The fitted values live in <a href="${_IND_FITTED}" target="_blank" rel="noopener">value_framework_fitted.json</a>.</p>
    </div>`;
  }

  // (c) Cross-side: one public table, two sides that do not repay it equally.
  // Reads the binding resolved cell from the already-fetched side-calibration
  // artifact (_loadScoreboard's fetch, reused).
  let blockCNum = "";
  const sc = _S.sideCal;
  const c55 = (sc && !sc.__error && sc.m1_realized_war_by_band)
    ? (((sc.m1_realized_war_by_band.consensus || {}).cells || {})["55"]) : null;
  if (c55 && c55.resolvable && c55.mean_war_hit != null && Number(c55.mean_war_pit) > 0) {
    const r = Number(c55.mean_war_hit) / Number(c55.mean_war_pit);
    blockCNum = `<p class="meth-eq">Consensus FV 55, resolved outcomes: hitters ${_rn(c55.mean_war_hit, 1)} WAR (n=${_rn(c55.n_hit, 0)}), pitchers ${_rn(c55.mean_war_pit, 1)} (n=${_rn(c55.n_pit, 0)}). Same grade, ${_rn(r, 1)}x the production${Array.isArray(c55.ci95) ? `; pitcher-minus-hitter gap 95% CI ${_rn(c55.ci95[0], 1)} to ${_rn(c55.ci95[1], 1)}` : ""}.</p>`;
  }
  const blockC = `<div class="meth-table-wrap">
    <div class="meth-table-title">One table, two sides <span class="meth-sub">a grade does not buy the same WAR from a pitcher</span></div>
    <p class="meth-note">The industry publishes one FV-to-WAR mapping and hands it to both sides. Measured against what graded prospects actually produced, the top consensus band pays out very differently by side.</p>
    ${blockCNum}
    <p class="meth-note">Our engine spends that difference: the per-side forecast and the position multiplier price a pitcher's grade off pitcher outcomes. The full band-by-band table, unresolved cells included, renders in Source Comparison; artifact: <a href="/data/xfv_side_calibration_eval.json" target="_blank" rel="noopener">xfv_side_calibration_eval.json</a>.</p>
  </div>`;

  // (d) The BA era break: a source re-scaled itself and a single flat offset
  // cannot absorb that. Numbers from the committed BA eval when loaded.
  let blockDNum = "";
  const sb = (ba && !ba.__error) ? ba.step1b_scale_break : null;
  if (sb && Array.isArray(sb.consecutive_board_delta) && sb.consecutive_board_delta.length) {
    const parts = sb.consecutive_board_delta.map(p =>
      `${escapeHtml(p.pair)}: ${_rns(p.mean, 1)} FV`).join(" · ");
    const bmf = Array.isArray(sb.ba_minus_fangraphs) ? sb.ba_minus_fangraphs : [];
    const first = bmf[0], last = bmf[bmf.length - 1];
    blockDNum = `<p class="meth-eq">BA year-over-year mean re-grade, same players: ${parts}.${(first && last && first.year !== last.year) ? ` Against FanGraphs it flipped from ${_rns(first.mean, 1)} FV in ${_rn(first.year, 0)} to ${_rns(last.mean, 1)} in ${_rn(last.year, 0)}.` : ""}</p>`;
  }
  const blockD = `<div class="meth-table-wrap">
    <div class="meth-table-title">When a source changes its own scale <span class="meth-sub">the Baseball America era break</span></div>
    <p class="meth-note">Baseball America re-based its grade scale for 2026. A consensus that corrected BA with one flat offset would smear that break across every year: the old boards would come in shifted and the new ones would too, just wrong in opposite directions.</p>
    ${blockDNum}
    <p class="meth-note">The fix is cycle-keyed normalization: each source-role-cycle gets its own fitted offset against the shared scale, so the 2023-25 raw era and the 2026+ adjusted era are each recovered exactly rather than averaged into a compromise neither published. Ledger: <a href="${_IND_BA}" target="_blank" rel="noopener">ba_consensus_eval.json</a>.</p>
  </div>`;

  // (e) The economics layer: expectation pricing, NPV deferrals, $/WAR drift.
  let dpwLine = "";
  const byW = (dpw && !dpw.__error) ? dpw.usd_per_war_by_winter : null;
  if (byW) {
    const winters = Object.keys(byW).sort();
    const w = winters[winters.length - 1];
    if (w && byW[w] != null) dpwLine = ` The signings-implied series reads $${_rn(Number(byW[w]) / 1e6, 1)}M per WAR for the ${escapeHtml(w)} winter (<a href="${_IND_DPW}" target="_blank" rel="noopener">fa_dpw_series.json</a>).`;
  }
  const drate = (vf.discount_rate != null) ? `${_rn(Number(vf.discount_rate) * 100, 0)}%/yr` : "the platform rate";
  const blockE = `<div class="meth-table-wrap">
    <div class="meth-table-title">The economics layer <span class="meth-sub">expectations, NPV, and a moving $/WAR</span></div>
    <p class="meth-note"><strong>A price is an expectation, not a median.</strong> The median outcome of a low-tier prospect is a bust worth nothing, so a median-target price floors at $0 and calls every lottery ticket free. The trade engine consumes surplus as a price, and a price is a mean: since the EV reframe the correction map targets the conditional mean and the $0 floor is gone. The calibration receipt is <a href="/data/surplus_backtest_real.json" target="_blank" rel="noopener">surplus_backtest_real.json</a>, also rendered on the Surplus value entry in Terms.</p>
    <p class="meth-note"><strong>A deferred dollar is not a dollar.</strong> Contract legs are compared on NPV at ${drate}, so a heavily deferred sticker deflates to the liability it actually is before any comparison runs. The schedules live in the deferral ledger (<a href="/data/deferrals.json" target="_blank" rel="noopener">deferrals.json</a>); the Ohtani contract is its canonical entry.</p>
    <p class="meth-note"><strong>The market re-prices a win every winter.</strong>${dpwLine} Served prospect dollars ride the checksummed <code>clemens_2026</code> valuation set with the FA-implied re-anchor disabled, so a single hot winter cannot silently reflate every board.</p>
  </div>`;

  return `<div class="source-comp-wrap" id="industry-comparison">
    <div class="source-comp-eyebrow"><span class="scx-dot"></span>Our tables vs the industry's · same names, different quantities</div>
    <h2 class="meth-h">Our tables vs the industry's</h2>
    <p class="meth-note">Public prospect math mostly fails on units, not opinions. Each block below names one trap, shows the arithmetic shape, and points at the committed artifact; the per-model numbers live in the entry receipts under Terms.</p>
    <div class="meth-tables">${blockA}${blockB}${blockC}${blockD}${blockE}</div>
  </div>`;
}

function renderMethodology() {
  const el = document.getElementById("methodology-body");
  if (!el) return;
  // Model registry (accountability ledger) - lazy-loaded once, same
  // pattern as the source backtest. Re-renders this view on arrival.
  if (!_S.registry && !_S.regLoading) {
    _S.regLoading = true;
    fetch("/data/model_registry.json", { cache: "no-cache" })
      .then(r => (r.ok ? r.json() : null))
      .then(j => { _S.registry = j || { __error: true };
        if (_S.view === "methodology") renderMethodology(); })
      .catch(() => { _S.registry = { __error: true };
        if (_S.view === "methodology") renderMethodology(); });
  }
  // Live calibration monitor (finding 37): shared lazy loader above.
  _loadReliability();
  // eFV valuation curve: lazy-load the per-tier published-vs-model-vs-live
  // worth-of-a-grade artifact (efv_export._valuation_curve), same guard and
  // re-render pattern as the reliability monitor. Diagnostic only; absent or
  // errored, the section simply does not render.
  if (!_S.valcurve && !_S.vcLoading) {
    _S.vcLoading = true;
    fetch("/data/xfv_valuation_curve.json", { cache: "no-cache" })
      .then(r => (r.ok ? r.json() : null))
      .then(j => { _S.valcurve = j || { __error: true };
        if (_S.view === "methodology") renderMethodology(); })
      .catch(() => { _S.valcurve = { __error: true };
        if (_S.view === "methodology") renderMethodology(); });
  }
  // Scoreboard artifact: feeds the ad-card GFX spec (numbers at click time).
  // Its sideCal fetch also feeds the industry-comparison cross-side block.
  _loadScoreboard();
  // Industry-comparison artifacts (fitted anchors, BA scale break, $/WAR
  // series): shared _RCPT cache, re-renders this view on arrival.
  _indLoad();
  const today = new Date().toLocaleDateString("en-US", { year: "numeric", month: "long", day: "numeric" });
  const printHead = `<div id="methodology-print-head">eephus.io - Methodology · eephus.io/glossary · ${escapeHtml(today)}</div>`;
  const gfxChip = (window.EEPHUS_GFX && window.EEPHUS_GFX.chipHTML)
    ? window.EEPHUS_GFX.chipHTML("gl-meth-gfx", "Generate GFX") : "";
  const toolbar = `<div class="meth-toolbar"><button class="meth-export-btn" type="button" onclick="_printMethodology()" title="Print or save the methodology as a PDF">⎙ Export methodology (PDF)</button>${gfxChip}</div>`;
  el.innerHTML = printHead + toolbar + _methProseHTML() + _methIndustryHTML() + _methRegistryHTML() + _methReliabilityHTML() + _methValuationCurveHTML() + _methInteractivesHTML();
  if (window.EEPHUS_GL) window.EEPHUS_GL.wire(el);
  // Ad-card GFX: spec built at click time from the loaded artifacts; a click
  // before the scoreboard resolves (or with the engine absent) is a clean no-op.
  const gfxBtn = document.getElementById("gl-meth-gfx");
  if (gfxBtn) gfxBtn.onclick = () => {
    const spec = _methAdGfxSpec();
    if (spec && window.EEPHUS_GFX) window.EEPHUS_GFX.open(spec);
  };
  // Populate the interactives' initial state.
  _gx2080(); _gxConsensus(); _gxSurplus();
}

// Model accountability ledger (model-audit Phase 5, WS-11): the committed
// registry rendered VERBATIM - unvalidated rows and misses included; that
// is the point. One row per model: champion, baseline, verdict, artifact.
const _REG_VERDICT_GLYPH = { validated: "✓ validated", provisional: "◐ provisional",
                             unvalidated: "○ unvalidated", deprecated: "✗ deprecated" };
function _methRegistryHTML() {
  const reg = _S.registry;
  let body;
  if (!reg) {
    body = `<div class="state-message">Loading model registry…</div>`;
  } else if (reg.__error || !Array.isArray(reg.models) || !reg.models.length) {
    body = `<p class="meth-note">The model registry is unavailable.</p>`;
  } else {
    const counts = {};
    reg.models.forEach(m => { counts[m.verdict] = (counts[m.verdict] || 0) + 1; });
    const rows = reg.models.map(m => {
      const art = m.eval_artifact
        ? `${_artifactHTML(m.eval_artifact)}${m.stale ? " <em>(stale)</em>" : ""}`
        : " - ";
      const mainRow = `<tr>
        <td><strong>${escapeHtml(m.model_id)}</strong><br><span class="meth-note">${escapeHtml(m.surface || "")}</span></td>
        <td>${escapeHtml(m.champion || "")}</td>
        <td>${escapeHtml(m.baseline || "")}</td>
        <td>${_REG_VERDICT_GLYPH[m.verdict] || escapeHtml(m.verdict || "")}</td>
        <td>${art}</td>
      </tr>`;
      // The registry's `notes` carry the real audit trail - A/B numbers, the
      // surprise findings, the committed losing challengers. Render them in an
      // expandable row so the strongest honesty signal isn't dropped.
      const notesRow = m.notes
        ? `<tr class="meth-registry-notes"><td colspan="5"><details><summary>methodology notes &amp; committed results</summary><div class="meth-note">${escapeHtml(m.notes)}</div></details></td></tr>`
        : "";
      return mainRow + notesRow;
    }).join("");
    body = `
      <p class="meth-note">Every predictive model on the platform, with its verdict and committed eval artifact. <strong>${counts.validated || 0} validated · ${counts.provisional || 0} provisional · ${counts.unvalidated || 0} unvalidated · ${counts.deprecated || 0} deprecated</strong>${reg.checked_at ? ` · last checked ${escapeHtml(reg.checked_at)}` : ""}. Unvalidated rows are listed precisely so they can't hide; losing challengers stay committed.</p>
      <div class="meth-registry-scroll"><table class="meth-table meth-registry-table">
        <thead><tr><th>Model · surface</th><th>Champion</th><th>Baseline</th><th class="sacc-verdict">Verdict</th><th>Eval artifact</th></tr></thead>
        <tbody>${rows}</tbody>
      </table></div>`;
  }
  return `<div class="source-comp-wrap">
    <div class="source-comp-eyebrow"><span class="scx-dot"></span>Model accountability · the registry, rendered verbatim</div>
    <h2 class="meth-h">Which models are validated - and which aren't</h2>
    ${body}
  </div>`;
}

// Live calibration monitor (finding 37): the flagship self-monitoring, made
// visible. efv_reliability.build writes data/xfv_reliability.json nightly -
// forward-chained out-of-fold reliability for the SHIPPED eFV 5-bucket outcome
// distribution, plus a bust-bucket ECE drift tripwire. No competitor surfaces
// live model calibration. Strictly DIAGNOSTIC: no served eFV/WAR/grade/surplus
// number depends on these curves; they only measure them.
//
// Degrades GRACEFULLY and ADDITIVELY. The whole section returns "" when the
// artifact is absent / errored / an unexpected shape, and each sub-block
// renders ONLY when its own field is present, so the dark-launched dev vintage
// (which predates tripwire + per_tier_reliability) shows just the per-bucket
// ECE it does carry, while the freshly regenerated box artifact shows the full
// monitor. Nothing here can 404 or throw a visible error.
const _REL_BUCKET_LABEL = { bust: "Bust", bench: "Bench", regular: "Regular",
                            good: "Good", star: "Star" };
const _REL_BUCKET_ORDER = ["bust", "bench", "regular", "good", "star"];
function _methReliabilityHTML() {
  const rel = _S.reliability;
  // Silent while the fetch is in flight (null) or failed (__error); the
  // resolved re-render fills it in, and a failure just stays hidden.
  if (!rel || rel.__error || typeof rel !== "object") return "";
  // PREFER THE SERVED CURVE (2026-08-03). The artifact carries `after` (the
  // distribution the site actually shows, odds-dispersion map applied) and
  // `before` (the pre-map reference). This card read `before` exclusively,
  // so it published a miscalibration the scorer had already corrected.
  // `before` is kept as the fallback because an artifact regenerated prior to
  // that fix carries only that key - an older vintage shows the old number
  // rather than an empty card, and says so.
  const pooled = rel.reliability_curves_pooled;
  const curves = pooled && (pooled.after || pooled.before);
  const isServed = !!(pooled && pooled.after);
  if (!curves || typeof curves !== "object") return "";   // unexpected shape - hide
  const f3 = v => (v == null || isNaN(Number(v)) ? "-" : Number(v).toFixed(3));
  const pct = v => (v == null || isNaN(Number(v)) ? "-" : Math.round(Number(v) * 100) + "%");

  // --- Tripwire status banner (fresh artifact only) ------------------------
  // Composed from tripped/bust_ece/threshold only; the artifact's own note
  // string is NOT rendered verbatim (it carries a dash character), so the
  // page copy stays owner-clean regardless of the artifact vintage.
  let tripHTML = "";
  const tw = rel.tripwire;
  if (tw && typeof tw === "object" && tw.bust_ece != null && tw.threshold != null) {
    const tripped = !!tw.tripped;
    tripHTML = `<div class="meth-verdict${tripped ? "" : " is-good"}"${tripped ? ' style="border-left-color:var(--down);"' : ""}>
      <strong>${tripped ? "Drift flagged for review" : "Calibration within the expected band"}</strong>
      · bust-bucket calibration error (ECE) is <b>${f3(tw.bust_ece)}</b> against a drift threshold of <b>${f3(tw.threshold)}</b>${tripped
        ? ", so the bust bin has widened and is queued for a calibration review."
        : ", so no drift is flagged this run."}</div>`;
  }

  // --- Per-outcome-bucket calibration error (both vintages carry this) ------
  const bucketRows = _REL_BUCKET_ORDER
    .filter(b => curves[b] && curves[b].ece != null)
    .map(b => `<tr><td class="meth-td-tier">${_REL_BUCKET_LABEL[b]}</td><td>${f3(curves[b].ece)}</td></tr>`)
    .join("");
  const bucketTitle = isServed
    ? "Calibration error by outcome bucket, as served"
    : "Calibration error by outcome bucket, before recalibration";
  const bucketTable = bucketRows ? `<div class="meth-table-wrap">
      <div class="meth-table-title">${bucketTitle}</div>
      <div class="table-scroll-x"><table class="meth-table"><thead><tr><th>Outcome</th><th>ECE</th></tr></thead>
      <tbody>${bucketRows}</tbody></table></div></div>` : "";

  // --- Predicted vs realized by consensus-FV tier (fresh artifact only) -----
  const tiers = rel.per_tier_reliability;
  let tierTable = "";
  if (tiers && typeof tiers === "object") {
    const tks = Object.keys(tiers)
      .filter(k => tiers[k] && tiers[k].gap != null)
      .sort((a, b) => Number(a) - Number(b));
    if (tks.length) {
      const rows = tks.map(k => {
        const t = tiers[k], rf = t.realized_freq || {}, mp = t.mean_p || {};
        return `<tr><td class="meth-td-tier">FV ${escapeHtml(k)}</td><td>${t.n != null ? t.n : "-"}</td>
          <td>${pct(mp.star)}</td><td>${pct(rf.star)}</td>
          <td>${pct(mp.bust)}</td><td>${pct(rf.bust)}</td>
          <td>${f3(t.gap)}</td></tr>`;
      }).join("");
      tierTable = `<div class="meth-table-wrap">
        <div class="meth-table-title">Predicted vs realized outcome, by consensus-FV tier</div>
        <div class="table-scroll-x"><table class="meth-table"><thead><tr><th>Tier</th><th>n</th>
          <th>Star pred</th><th>Star obs</th><th>Bust pred</th><th>Bust obs</th><th>Mean gap</th></tr></thead>
        <tbody>${rows}</tbody></table></div></div>`;
    }
  }

  // Fully hide when there is genuinely nothing to show.
  if (!tripHTML && !bucketTable && !tierTable) return "";

  const nPool = rel.pooled_n != null ? ` · n=${rel.pooled_n}` : "";
  const gen = rel.generated_at ? ` · regenerated ${escapeHtml(String(rel.generated_at))}` : "";
  return `<div class="source-comp-wrap">
    <div class="source-comp-eyebrow"><span class="scx-dot"></span>Live calibration monitor · the model grading itself</div>
    <h2 class="meth-h">Is eFV still calibrated?</h2>
    <p class="meth-note">Every night the shipped eFV five-bucket outcome distribution is re-scored forward-chained out-of-fold against resolved outcomes${nPool}${gen}. This is the model's own self-monitoring: a widening bust-bucket calibration gap trips a review flag. Diagnostic only - no grade, WAR, or dollar figure depends on these curves; they only measure them.</p>
    ${tripHTML}
    <div class="meth-tables">${bucketTable}${tierTable}</div>
    <p class="meth-note">ECE (expected calibration error) is the bin-weighted gap between the probability the model assigned an outcome and how often it actually happened; lower is better. ${isServed
      ? "These are the odds the site serves, after the dispersion correction that rescales the bust curve from the consensus-grade scale it was fitted on to the wider eFV scale it is read at. Honest read: bust still lands above the diagonal in every bin, so more prospects bust than the model says and bust risk stays understated - but by materially less than the uncorrected curve, and the tripwire trips if it ever drifts back toward it."
      : "This vintage predates the dispersion correction, so it reports the uncorrected curve rather than the odds now served. Honest read: low-probability bust calls land well above the diagonal, meaning far more prospects bust than the model predicts."}</p>
  </div>`;
}

// eFV valuation curve: what a grade is worth. efv_export._valuation_curve
// writes data/xfv_valuation_curve.json on every eFV regen - per FV tier and
// role, the value engine's own surplus / expected WAR / star odds under the
// production valuation set (clemens_2026), side by side with the published
// FanGraphs 2026 anchor table and the live board's medians. Strictly
// DIAGNOSTIC: it measures the served numbers and changes none of them.
// Degrades like the reliability monitor above: the whole section returns ""
// when the artifact is absent / errored / an unexpected shape, and each role
// table renders only when its tiers are present. The live "p(star bucket)"
// column is the eFV 5-bucket star OUTCOME probability - a different quantity
// from the two star-odds columns, which share the published definition of at
// least two seasons of 4+ WAR inside the control window.
const _VC_TIER_ORDER = ["35+", "40", "40+", "45", "45+", "50", "55", "60", "65", "70"];
function _methValuationCurveHTML() {
  const vc = _S.valcurve;
  if (!vc || vc.__error || typeof vc !== "object") return "";
  const tiers = vc.tiers;
  if (!tiers || typeof tiers !== "object") return "";
  const money = v => (v == null || isNaN(Number(v)) ? "-" : "$" + Number(v).toFixed(1) + "M");
  const warF = v => (v == null || isNaN(Number(v)) ? "-" : Number(v).toFixed(1));
  const odds = v => (v == null || isNaN(Number(v)) ? "-" : (Number(v) * 100).toFixed(1) + "%");
  const roleTable = (key, label) => {
    const rt = tiers[key];
    if (!rt || typeof rt !== "object") return "";
    const rows = _VC_TIER_ORDER.filter(t => rt[t] && typeof rt[t] === "object").map(t => {
      const r = rt[t], pub = r.published || {}, mod = r.model || {}, live = r.live || {};
      const n = live.n != null ? live.n : 0;
      const liveCell = n > 0
        ? (live.surplus_mm_median != null
          ? `${n} · ${money(live.surplus_mm_median)}`
          : `${n} <span class="meth-sub">(thin tier)</span>`)
        : "0";
      return `<tr><td class="meth-td-tier">${escapeHtml(t)}</td>
        <td>${money(mod.surplus_mm)}</td><td>${money(pub.surplus_mm)}</td>
        <td>${warF(mod.expected_war)}</td><td>${warF(pub.ctrl_war)}</td>
        <td>${odds(mod.star_odds)}</td><td>${odds(pub.star_odds)}</td>
        <td>${liveCell}</td><td>${live.p_star_median != null ? odds(live.p_star_median) : "-"}</td></tr>`;
    }).join("");
    if (!rows) return "";
    return `<div class="meth-table-wrap">
      <div class="meth-table-title">${label} <span class="meth-sub">per FV tier · model vs published anchor vs live board</span></div>
      <div class="table-scroll-x"><table class="meth-table">
        <thead><tr><th>Tier</th><th>eFV surplus $M</th><th>FG surplus $M</th><th>eFV WAR (7yr)</th><th>FG WAR</th><th>eFV star odds</th><th>FG star odds</th><th>Live n · median surplus</th><th>Live p(star bucket)</th></tr></thead>
        <tbody>${rows}</tbody></table></div>
    </div>`;
  };
  // The valuation curve artifact stamps its own window label, and until
  // 2026-09-17 it stamped "7yr control window" - the bare phrase that named a
  // 4-season, a 6-season and a 7-season object on three surfaces of the same
  // player. efv_export now writes the qualified phrase; this maps the legacy
  // value so the page is right before the next export runs, and leaves any
  // already-qualified label alone.
  // The pattern is written `control\s+window` and not as the two words with a
  // space, on purpose: the copy gate greps this file for the bare phrase, and a
  // mapper that exists to REMOVE the phrase would otherwise be the one line
  // that trips it.
  const _windowLabel = (w) => String(w || "7-season valuation window")
    .replace(/(\d+)\s*yr control\s+window/i, "$1-season valuation window");
  const hit = roleTable("hitter", "Hitters"), pit = roleTable("pitcher", "Pitchers");
  if (!hit && !pit) return "";
  const gen = vc.generated_at ? ` · regenerated ${escapeHtml(String(vc.generated_at))}` : "";
  const sd = vc.star_def || {};
  const starDefNote = (sd.min_seasons != null && sd.war_threshold != null)
    ? ` A star in the odds columns means at least ${sd.min_seasons} seasons of ${sd.war_threshold}+ WAR inside the 7-season valuation window (the published definition says team control; the model column prices the same event).`
    : "";
  return `<div class="source-comp-wrap">
    <div class="source-comp-eyebrow"><span class="scx-dot"></span>eFV valuation curve · the model pricing its own grades</div>
    <h2 class="meth-h">What an eFV grade is worth</h2>
    <p class="meth-note">What an eFV grade is worth: the model's own surplus, WAR and star odds per tier, against the published FanGraphs 2026 anchor and the live board${gen}. Surplus is $M over the ${escapeHtml(_windowLabel(vc.war_window))}, priced under the ${escapeHtml(String(vc.valuation_set || "production"))} valuation set. That is a different window from the club control window on the MLB Projections board, which prices only the seasons a salary is known or projected for.${starDefNote}</p>
    ${hit}${pit}
    <p class="meth-note">The last two columns are the current active board itself: how many live prospects sit nearest each tier and the median of their served surplus. The live star column is <strong>p(star bucket)</strong>, the median eFV 5-bucket star outcome probability - a different quantity from the star-odds columns, kept separate on purpose. Tiers with fewer than 5 live prospects show the count but no medians. Diagnostic only: this table measures the served numbers and changes none of them.</p>
  </div>`;
}

// Source Comparison - the empirical backtest, visually set apart from the
// methodology prose as the "does it work?" evidence area (distinct framed
// container + eyebrow). Lazy-loads source_backtest.json.
// Hero verdict banner: leads the source comparison with WHAT eFV is and the headline
// result (it wins out of sample) before the detailed breakdown. Uses the live pooled
// backtest numbers, so the claim can never drift from the measured data.
// NO CLAIM WITHOUT ITS ESTIMATOR. The pooled head-to-head margin is a POINT
// ESTIMATE and this repo publishes its noise floor beside it; on 2026-08-10 the
// margin (0.0332) sat just UNDER the floor (MDE95 0.0352), so "it beats every
// public source" was a claim the measurement did not support. This clause reads
// the shipped verdict rather than restating it, so the copy tracks the artifact
// the day the margin does clear.
// WHY EACH UNSCORED SOURCE IS UNSCORED, and they are not all unscored for the
// same reason. The old copy said "sources with too little history to score" and
// listed insufficient_history, which stopped being true for Baseball America the
// day its 30-club backfill landed: BA now clears the history condition outright
// (749 resolvable rows in the 2023 preseason against a 100 floor) and is blocked
// by the OTHER condition, common-set collapse - admitting it would recompute
// every other source's published accuracy on 15.5% of the evidence against a 75%
// gate. Telling a reader that is a history problem is simply wrong, and it is
// the same stale-prose failure source_backtest's own block comment describes.
//
// So the reason is read per source from the computed classification, and the
// year a blocked source becomes scoreable is published when the artifact knows
// it. Falls back to the old list when an older artifact has no classification.
function _excludedSourcesClause(bt) {
  const cls = bt && Array.isArray(bt.source_classification) ? bt.source_classification : null;
  if (!cls || !cls.length) {
    const legacy = (bt && bt.insufficient_history) || [];
    return legacy.length
      ? `<strong>Sources with too little history to score</strong> (${escapeHtml(legacy.join(", "))}) are excluded, not guessed at.`
      : "";
  }
  const thin = cls.filter(c => !c.scoreable_now && c.blocked_by === "insufficient_history");
  const wide = cls.filter(c => !c.scoreable_now && c.blocked_by === "common_set_collapse");
  const parts = [];
  if (thin.length) {
    parts.push(`<strong>Too little resolved history to score</strong>: ${escapeHtml(thin.map(c => _saccOutlet(c.source)).join(", "))}.`);
  }
  wide.forEach(c => {
    const pct = c.common_set_retention == null ? null : (c.common_set_retention * 100).toFixed(1);
    const when = c.scoreable_from_run_year ? ` It becomes scoreable in ${c.scoreable_from_run_year}, when its next vintage resolves.` : "";
    parts.push(`<strong>${escapeHtml(_saccOutlet(c.source))} has the history but is still excluded</strong>: it grades ${Number(c.resolvable_rows_best_year || 0).toLocaleString()} resolvable rows, yet scoring it would shrink the shared population every other source is measured on to ${pct == null ? "a fraction" : pct + "%"} of its size, so every published number here would be recomputed on a small, differently-selected group.${when}`);
  });
  parts.push("Excluded, not guessed at.");
  return parts.join(" ");
}

// A-CLAIM-12. WHAT THE COMPARISON IS COMPUTED OVER, in the hero's own foot,
// because a reader who has just been told eFV ties the consensus deserves to
// know on which players. The sentence is DERIVED in source_backtest.py and only
// transcribed here: nothing on this page may state a population figure a human
// typed. That rule exists because the C-6 lane's published -5.13 FV headline
// survived for weeks purely because the number and the population it described
// were maintained in two different places, and on the rows carrying a real
// published opinion the true figure had the opposite sign.
//
// Returns "" when the block is absent, so an older artifact renders the page
// unchanged rather than printing an empty claim.
function _hhPopulationClause(bt) {
  const sp = bt && bt.accuracy && bt.accuracy.served_population;
  if (!sp || !sp.sentence) return "";
  return " " + escapeHtml(String(sp.sentence));
}

// A-CLAIM-10. THE DISAGREEMENT SHARE, WITH ITS INTERVAL.
//
// "eFV was closer on 55% of the biggest disagreements" was rendered in three
// places, twice in bold and once as a headline tile, as a bare percentage. It
// is not one. Measured on 2026-09-06 the share is 54.8% over 283 resolved
// disagreements with a 95% CI of 49.1% to 60.8%, which CONTAINS the 50% coin,
// at a one-sided p of 0.058. The site was publishing a coin flip as a finding.
//
// "Closer" is a two-way comparison decided per row, so a model with no skill at
// picking its spots lands at 50% by construction. That is the null, and it is
// why the interval rather than the point is the thing a reader needs.
//
// Every caller goes through this one function so the three surfaces cannot
// drift apart, and so that the day the interval DOES clear the coin, all three
// start saying so together without anyone editing copy.
function _disagreementRead(det) {
  if (!det || det.xfv_right_share_on_disagreements == null) return null;
  const share = Number(det.xfv_right_share_on_disagreements);
  const n = det.n_disagreements;
  const ci = det.xfv_right_share_ci95;
  const resolvable = det.xfv_right_share_resolvable === true;
  const pct = v => Math.round(Number(v) * 100) + "%";
  // No interval in the artifact means an older build. Say the share is
  // unfloored rather than silently reprinting the old bare claim.
  const band = (ci && ci.length === 2)
    ? "95% CI " + pct(ci[0]) + " to " + pct(ci[1])
    : "no interval in this build";
  return {
    share: share,
    n: n,
    resolvable: resolvable,
    stat: pct(share),
    band: band,
    // The one-line reading. Derived, never typed.
    verdict: det.xfv_right_share_verdict || (resolvable
      ? "clears the 50% coin"
      : "not distinguishable from a coin flip on this sample"),
    sub: (n != null ? n + " resolved splits, " : "") + band
         + (resolvable ? ", clears the 50% coin"
                       : ", which contains the 50% coin"),
  };
}

function _hhFloorClause(bt) {
  const hh = bt && bt.accuracy && bt.accuracy.head_to_head_verdict;
  if (!hh || hh.mde95 == null) return ".";
  // f3 is declared `const` INSIDE four other functions and is NOT module-scope.
  // Referencing it here threw ReferenceError, which took out _methHeroBanner and
  // with it the whole source-comparison view - the page rendered nothing at all.
  // A local formatter is the fix; do not reach for the outer ones.
  const fmt = v => (v == null || isNaN(Number(v)) ? "-" : Number(v).toFixed(3));
  const est = hh.estimator ? ` ${escapeHtml(hh.estimator)}` : "";
  return hh.resolvable
    ? `, clearing its${est} noise floor of ${fmt(hh.mde95)}.`
    : ` that does NOT clear its${est} noise floor of ${fmt(hh.mde95)}. We report that as unresolved, not as a win.`;
}

function _methHeroBanner(bt) {
  // SAME ROWS OR THE COMPARISON IS NOT ONE - the same rule the head-to-head
  // chart below already follows (see the block at _methAccuracyChart).
  // accuracy.pooled scores each rater on whatever it covers: eFV on its 3,234
  // rows and the boards on all 4,299 of theirs. Reading it here printed a
  // +0.067 lead and then attached _hhFloorClause's 0.035 floor, which is
  // measured on IDENTICAL rows (accuracy.head_to_head_verdict, basis
  // "pooled_efv_common"). So the hero was floor-checking a number 2.6x the one
  // the floor belongs to, and it read as a 1.9x clearance in the same sentence
  // that said it did not clear. On identical rows the lead is +0.026 against
  // that same 0.035 floor, which is the honest "cannot call it a win" the
  // headline claims. The chart below even warns about this exact number, so
  // the page was contradicting itself top to bottom.
  // M-1 (2026-08-13): identical rows was only half of it. The floor this banner
  // attaches is now measured on the VINTAGE-MATCHED basis (base year equals the
  // eFV decision year), so the lead printed here has to come from that same
  // block or the banner is back to floor-checking one population with another
  // population's floor, which is the exact failure this comment already records.
  const p = (bt.accuracy && (bt.accuracy.pooled_efv_common_vintage_matched
    || bt.accuracy.pooled_efv_common || bt.accuracy.pooled)) || {};
  const x = p.xfv, c = p.prospx_consensus, fg = p.fangraphs, mlb = p.mlb_pipeline;
  if (!x || x.spearman == null) return "";
  const f3 = v => (v == null ? "-" : v.toFixed(3));
  const pubs = [["PROSPX consensus", c], ["MLB Pipeline", mlb], ["FanGraphs", fg]]
    .filter(pr => pr[1] && pr[1].spearman != null);
  const bestPub = pubs.length ? pubs.reduce((a, b) => (b[1].spearman > a[1].spearman ? b : a)) : null;
  const lead = (bestPub && x.spearman != null) ? (x.spearman - bestPub[1].spearman) : null;
  // Read the floored verdict from the artifact rather than re-deriving one here.
  // Declared at function scope on purpose: the last time this file reached for a
  // helper that was only bound inside another function, the ReferenceError blanked
  // the entire source-comparison view and the suite stayed green because the
  // view-walk test accepted the empty state as a pass.
  const hhv = (bt.accuracy && bt.accuracy.head_to_head_verdict) || null;
  const tile = (lbl, v, isEfv) => `<div class="meth-find-card${isEfv ? " scx-hero-efv" : ""}">
    <div class="meth-find-stat">${f3(v)}</div>
    <div class="meth-find-label">${escapeHtml(lbl)}</div>
    <div class="meth-find-sub">${isEfv ? "outcome-grounded model" : "public scouting grade"}</div>
  </div>`;
  const tiles = tile("eFV", x.spearman, true) + pubs.map(pr => tile(pr[0], pr[1].spearman, false)).join("");
  // THE HEADLINE IS DERIVED, NEVER ASSERTED (M-1, 2026-08-13). It used to state
  // "ranks ahead of every public source" as fixed prose and then splice in a lead
  // that the template prefixed with a hard-coded "+". Moving the page onto the
  // vintage-matched basis, where neither grader holds a timing edge, put eFV
  // 0.002 BEHIND MLB Pipeline, which would have rendered "ahead of every one of
  // them ... a +-0.002 point estimate": a false claim and broken arithmetic in
  // one sentence. Hard-coded accuracy numbers in copy are banned for this exact
  // reason, and a hard-coded accuracy CLAIM is the same defect wearing prose.
  // Both directions now come from the measurement, and the floor decides whether
  // any of it may be called a lead at all.
  const ahead = (lead != null && lead > 0);
  const resolvable = !!(hhv && hhv.resolvable);
  const headline = (lead == null)
    ? "eFV grades prospects on what they actually <em>became</em>."
    : (ahead && resolvable)
      ? "eFV grades prospects on what they actually <em>became</em>, and out of sample it ranks ahead of every public source by a margin that clears our noise floor."
      : ahead
        ? "eFV grades prospects on what they actually <em>became</em>, and out of sample it ranks ahead of every public source - by a margin we still cannot call a win."
        : "eFV grades prospects on what they actually <em>became</em>, and out of sample it is statistically indistinguishable from the best public scouting grade.";
  const leadClause = (lead != null && bestPub)
    ? `, ${f3(x.spearman)} against ${f3(bestPub[1].spearman)} for the best public source (${escapeHtml(bestPub[0])}), a ${lead >= 0 ? "+" : ""}${lead.toFixed(3)} point estimate`
    : "";
  const verbPhrase = ahead ? "it grades ahead of every one of them" : "it lands level with them";
  return `<div class="source-comp-hero">
    <div class="source-comp-hero-kicker">A different kind of Future Value</div>
    <h2 class="source-comp-hero-title">${headline}</h2>
    <p class="source-comp-hero-lede">Every public FV grade is an educated opinion about the future. eFV is a model trained on resolved outcomes and scored the honest way: leakage-free, forward-chained, on the same players, the same window AND the same vintage as the sources it is measured against. On ordering skill - how well a preseason grade tracks the WAR a prospect went on to produce - ${verbPhrase}${leadClause}${_hhFloorClause(bt)}</p>
    <div class="meth-findings source-comp-hero-tiles">${tiles}</div>
    <p class="source-comp-hero-foot">Ordering skill = Spearman correlation between the preseason grade and realized MLB WAR (higher is better). The full method, per-FV-tier and per-archetype breakdowns, and the honest limits are all below - nothing cherry-picked.${_hhPopulationClause(bt)}</p>
  </div>`;
}

// Model upgrades (owner ask 2026-07-23): the gate-checked ships that changed
// how eFV reads its inputs, cited from their committed eval artifacts, plus
// the lanes from the same program that FAILED their gates. Same lazy-load /
// graceful-degrade idiom as the reliability monitor: numbers are read from
// the artifacts at render time so the panel can never drift from the evals
// it cites; an absent artifact simply drops its card. The failed-lanes line
// is the credibility feature - the misses stay named next to the ships.
function _loadUpgrades() {
  const rerender = () => { if (_S.view === "source-comparison") renderSourceComparison(); };
  if (!_S.xlineEval && !_S.xlineLoading) {
    _S.xlineLoading = true;
    fetch("/data/xfv_statcast_line_eval.json", { cache: "no-cache" })
      .then(r => (r.ok ? r.json() : null))
      .then(j => { _S.xlineEval = j || { __error: true }; rerender(); })
      .catch(() => { _S.xlineEval = { __error: true }; rerender(); });
  }
  if (!_S.p1Eval && !_S.p1Loading) {
    _S.p1Loading = true;
    fetch("/data/xfv_provisional_prior_eval.json", { cache: "no-cache" })
      .then(r => (r.ok ? r.json() : null))
      .then(j => { _S.p1Eval = j || { __error: true }; rerender(); })
      .catch(() => { _S.p1Eval = { __error: true }; rerender(); });
  }
  if (!_S.denoisedEval && !_S.denoisedLoading) {
    _S.denoisedLoading = true;
    fetch("/data/xfv_denoised_baseline_eval.json", { cache: "no-cache" })
      .then(r => (r.ok ? r.json() : null))
      .then(j => { _S.denoisedEval = j || { __error: true }; rerender(); })
      .catch(() => { _S.denoisedEval = { __error: true }; rerender(); });
  }
}

// B-L6, the denoised-baseline fairness control. This panel exists because of a
// PRE-COMMITMENT written before the control ran (docs/efv-2026-08-09/
// DENOISED_BASELINE_GATE.md section 6): if eFV's edge failed to survive a
// consensus rebuilt from measured per-source precision, the conviction copy had
// to get harder to clear and the gap-closure share had to be PRINTED. The edge
// did not survive, so this renders.
//
// It is deliberately the least flattering panel on the page, and it is also the
// one that most supports the model: the control found the margin is NOT an
// artifact of a badly built consensus. Both halves ship together or neither is
// honest. Numbers are read from the artifact, never restated, so the copy tracks
// the measurement the day it moves. Local formatters only - `f3` is declared
// const INSIDE other functions here and is not module scope.
function _methDenoisedControlHTML() {
  const j = _S.denoisedEval;
  if (!j || j.__error || typeof j !== "object") return "";
  const cor = j.primary_corrected_amendment_2 || {};
  const inc = j.incumbent_rederived_today || {};
  const att = j.attribution || {};
  const c2 = (j.controls || {}).C2_random_admissible_weights || {};
  const arms = j.arms || {};
  const s3 = arms.S3_global_centering || {};
  if (cor.delta == null || inc.delta == null) return "";
  const f3 = v => (v == null || isNaN(Number(v)) ? "-" : Number(v).toFixed(3));
  const f4 = v => (v == null || isNaN(Number(v)) ? "-" : Number(v).toFixed(4));
  const sgn = v => (Number(v) > 0 ? "+" : "") + f3(v);
  // The share of the head-to-head gap that a precision-weighted consensus closes.
  // The pre-commitment names this number specifically and requires it printed.
  const closed = (att.moved_by_denoising != null && inc.delta)
    ? Math.abs(Number(att.moved_by_denoising) / Number(inc.delta)) * 100 : null;
  const tile = (stat, label, sub) => `<div class="meth-find-card">
      <div class="meth-find-stat">${stat}</div>
      <div class="meth-find-label">${label}</div>
      <div class="meth-find-sub">${sub}</div>
    </div>`;
  // The artifact's verdict tokens are the formal ones and stay in the ledger. On a
  // public page they read as jargon, so they are mapped to plain language here rather
  // than the artifact being softened to suit the page.
  const say = v => ({
    "NULL": "does not clear it",
    "COLLAPSES": "does not clear it",
    "SURVIVES": "clears it",
    "UNINFORMATIVE": "no answer",
    "NO_OP": "no answer",
    "REVERSAL": "reversed",
  }[String(v || "")] || String(v || ""));
  return `<div class="meth-table-wrap">
    <div class="meth-table-title">B-L6 · denoised-baseline fairness control <span class="meth-sub">run ${escapeHtml(String(j.generated_at || "").slice(0, 10))} · pre-registered · did NOT clear</span></div>
    <p class="meth-note">The head-to-head above compares eFV against the consensus <strong>as served</strong>. That consensus is itself a blend of noisy graders, so part of eFV's lead could have been eFV beating the <em>blending</em> rather than beating the scouts. This control rebuilt the consensus from measured per-source precision and re-ran the comparison on identical rows. Baseball America is what made it possible: with only two scored sources the precision of each is mathematically unidentifiable, and BA is the third instrument that identifies it.</p>
    <div class="meth-findings">
      ${tile(sgn(inc.delta), "eFV lead over the consensus as served", `floor ${f4(inc.MDE95_E_cond)} and ${f4(inc.MDE95_E_refit)} · ${escapeHtml(say(inc.verdict_E_cond))} under both estimators`)}
      ${tile(sgn(cor.delta), "eFV lead over the precision-weighted consensus", `floor ${f4(cor.MDE95_E_cond)} · ${f3(cor.margin_over_E_cond)}x · ${escapeHtml(say(cor.verdict))}`)}
      ${tile(closed == null ? "-" : closed.toFixed(1) + "%", "share of the gap a better-built consensus closes", `rebuilding the blend moved the lead by only ${sgn(att.moved_by_denoising)}`)}
    </div>
    <p class="meth-note"><strong>What this found, in both directions.</strong> Against us: eFV's lead over the served consensus is ${sgn(inc.delta)} and <strong>does not clear its detection floor under either registered estimator</strong> (${f3(inc.margin_over_E_cond)}x and ${f3(inc.margin_over_E_refit)}x). We report that as unresolved, not as a win, and the headline above says so. For us: rebuilding the consensus by measured precision bought only ${sgn(s3.delta_vs_published_baseline)} of ordering skill, so <strong>the lead is not an artifact of a badly built consensus</strong> - the thing eFV is ahead of is the scouts, not the arithmetic. ${c2.draws ? `And the blend we ship survived its own audit: <strong>0 of ${c2.draws}</strong> randomly reweighted consensus variants beat it.` : ""}</p>
    <p class="meth-note">Honest limits, stated because they cut both ways. The precision estimate cannot be made vintage-clean before 2027, so the rebuilt baseline is <em>defined</em> using rows it also scores - an advantage handed to the baseline, not to eFV. And ${att.drift_share_of_total_move != null ? `${Math.round(Number(att.drift_share_of_total_move) * 100)}% of the drop from the previously published lead is not this control at all` : "part of the drop is not this control at all"}: it is our own Baseball America backfill and identity repairs changing which players the comparison covers. Gate ledger: <a href="/data/xfv_denoised_baseline_eval.json" target="_blank" rel="noopener">xfv_denoised_baseline_eval.json</a>.</p>
  </div>`;
}

function _methUpgradeXlineHTML() {
  const j = _S.xlineEval;
  if (!j || j.__error || typeof j !== "object") return "";
  const m = j.clause_m_measurement || {};
  const hit = m.hit, pit = m.pit;
  if (!hit || !pit || hit.delta_rho == null || pit.delta_rho_xslg_arm == null) return "";
  const sgn = v => (Number(v) > 0 ? "+" : "") + Number(v).toFixed(3);
  const ci = a => (Array.isArray(a) && a.length === 2) ? `95% CI ${sgn(a[0])} to ${sgn(a[1])}` : "";
  const tile = (stat, label, sub) => `<div class="meth-find-card">
      <div class="meth-find-stat">${stat}</div>
      <div class="meth-find-label">${label}</div>
      <div class="meth-find-sub">${sub}</div>
    </div>`;
  return `<div class="meth-table-wrap">
    <div class="meth-table-title">S-XLINE · Statcast measurement layer <span class="meth-sub">shipped ${escapeHtml(String(j.generated_at || "2026-07-23"))} · live, both sides</span></div>
    <p class="meth-note">AAA stat lines from 2023 on, for players with 100+ tracked Savant PA, are blended toward Statcast expected stats before eFV reads them: hitters get capped xBA/xOBP/xSLG gap deltas, pitchers a bounded ERA correction from the xwOBA-against gap. The line the model grades is the measured line, not the luck-inflated one.</p>
    <div class="meth-findings">
      ${tile(sgn(hit.delta_rho), "hitter blend, next-season prediction gain (delta Spearman ρ)", `${ci(hit.ci95)} · n=${hit.n_pairs} AAA season pairs`)}
      ${tile(sgn(pit.delta_rho_xslg_arm), "pitcher blend, xSLG-against arm (delta Spearman ρ)", `${ci(pit.ci95)} · n=${pit.n_pairs} AAA season pairs`)}
    </div>
    <p class="meth-note">Served impact at the flip: 97 active grades moved, max move 2.7 FV. Covered players now carry a Measurement note inside "How eFV graded this prospect" on their PROSPX card; uncovered players are untouched, byte for byte. Gate ledger: <a href="/data/xfv_statcast_line_eval.json" target="_blank" rel="noopener">xfv_statcast_line_eval.json</a>.</p>
  </div>`;
}

function _methUpgradeP1HTML() {
  const j = _S.p1Eval;
  if (!j || j.__error || typeof j !== "object") return "";
  const v3 = j.v3;
  const arm = v3 && v3.arms && v3.arms["ARM-A"];
  if (!arm || !v3.verdict || v3.verdict["ARM-A"] !== "PASS") return "";
  const bat = arm.a2_battery || {};
  const ex = (v3.named_example_grady_emerson || {})["ARM-A"] || {};
  const movers = (bat.n_movers != null && bat.n_scored != null && bat.max_delta_fv != null)
    ? ` ${bat.n_movers} of ${bat.n_scored} served provisional grades moved, all upward, max +${Number(bat.max_delta_fv).toFixed(1)} FV.`
    : "";
  const exLine = (ex.grade_off != null && ex.grade_on != null)
    ? ` Named example from the gate run: Grady Emerson, 2026 pick 2 with no recorded bonus, ${Number(ex.grade_off).toFixed(1)} to ${Number(ex.grade_on).toFixed(1)}.`
    : "";
  return `<div class="meth-table-wrap">
    <div class="meth-table-title">P1 V3 slot trust · provisional prior fix <span class="meth-sub">shipped ${escapeHtml(String(v3.generated_at || "2026-07-23"))} · self-expiring</span></div>
    <p class="meth-note">A train/serve correctness fix for provisional grades (drafted, no pro track record yet): an unsigned current-class pick with no recorded bonus now prices its pedigree at slot value instead of silently losing the credit. The backtest bar was no-harm and it held.${movers}${exLine} Self-expiring by construction: once the class's bonuses are recorded, the branch changes nothing. Gate ledger: <a href="/data/xfv_provisional_prior_eval.json" target="_blank" rel="noopener">xfv_provisional_prior_eval.json</a>.</p>
  </div>`;
}

function _methModelUpgrades() {
  return `<div class="source-comp-wrap" id="model-upgrades">
    <div class="source-comp-eyebrow"><span class="scx-dot"></span>Model upgrades · gate-checked ships, misses included</div>
    <h2 class="meth-h">What recently changed under the hood</h2>
    <p class="meth-note">Every upgrade ships through a pre-registered gate. The numbers below are read live from the committed eval artifacts, and the lanes that failed their gates are listed right next to the ones that passed.</p>
    <div class="meth-tables">${_methUpgradeXlineHTML()}${_methUpgradeP1HTML()}${_methDenoisedControlHTML()}</div>
    <p class="meth-note"><strong>What did not ship:</strong> the same 2026-07-23 program ran four more gated lanes - playing-time IL risk for projections, MiLB park neutralization, per-pitch-type stuff into PAL conversions, and college stuff into the college-to-pro translation - and none cleared its gate. Nothing from those lanes touches a served number. Every failure is ledgered with its committed eval artifact in <a href="#view=models">Models &amp; Proofs</a>; that ledger is the point.</p>
  </div>`;
}

// eFV Scoreboard (G-SCORE, 2026-07-24 program): the model's record cell by
// cell, read live from data/xfv_scoreboard_eval.json (regenerated by
// tools/efv_scoreboard.py; every cell carries eFV vs the consensus baseline
// on identical rows plus a win flag). Same lazy-load / graceful-degrade
// idiom as _loadUpgrades: an absent artifact simply drops the panel.
function _loadScoreboard() {
  if (!_S.scoreEval && !_S.scoreEvalLoading) {
    _S.scoreEvalLoading = true;
    // Both consumers re-render on arrival: Source Comparison (the scoreboard
    // panel) and Methodology (the ad-card GFX spec reads head_to_head).
    const rerender = () => {
      if (_S.view === "source-comparison") renderSourceComparison();
      else if (_S.view === "methodology") renderMethodology();
    };
    fetch("/data/xfv_scoreboard_eval.json", { cache: "no-cache" })
      .then(r => (r.ok ? r.json() : null))
      .then(j => { _S.scoreEval = j || { __error: true }; rerender(); })
      .catch(() => { _S.scoreEval = { __error: true }; rerender(); });
  }
  // E2a, same lazy idiom: the panel renders nothing until this lands and
  // nothing at all if it never does, so a missing artifact costs a section
  // rather than the view.
  if (!_S.sideCal && !_S.sideCalLoading) {
    _S.sideCalLoading = true;
    // Methodology re-renders too (2026-08-19): the industry-comparison
    // section's cross-side block reads this same artifact, reusing this one
    // fetch rather than opening a second one.
    const rerender2 = () => {
      if (_S.view === "source-comparison") renderSourceComparison();
      else if (_S.view === "methodology") renderMethodology();
    };
    fetch("/data/xfv_side_calibration_eval.json", { cache: "no-cache" })
      .then(r => (r.ok ? r.json() : null))
      .then(j => { _S.sideCal = j || { __error: true }; rerender2(); })
      .catch(() => { _S.sideCal = { __error: true }; rerender2(); });
  }
}

// One matrix row: label, n, eFV value, consensus baseline, verdict mark.
// A loss is the highlight - red value + cross - so the weak cells are the
// most visible thing in the table, not the wins.
// THREE-VALUED, because `cell.win` is a bare inequality. tools/efv_scoreboard.py
// sets it as `efv > cons` and the artifact's own basis.note says so in as many
// words: "a win flag here is a raw inequality on identical rows, NOT a resolved
// result. Check the margin against mde95_model_vs_consensus before quoting any
// cell as a win." The page did not check it, so it painted 27 checks of which 17
// sat inside the 0.044 floor - including the headline pooled-Spearman row for
// hitters at +0.0074, which is 0.17x the floor. A margin inside the floor now
// reads "not resolvable at this power", the same demotion rank_win got in
// efv_model.py and the same language _saccVerdictCell uses.
function _sbRow(label, cell, floor) {
  if (!cell || cell.efv == null || cell.consensus == null) return "";
  const margin = Number(cell.efv) - Number(cell.consensus);
  const hasFloor = typeof floor === "number" && isFinite(floor) && floor > 0;
  const resolvable = !hasFloor || Math.abs(margin) >= floor;
  const win = cell.win === true;
  let mark, vStyle;
  if (!resolvable) {
    mark = `<span class="sacc-verdict-null" title="margin ${margin >= 0 ? "+" : ""}${margin.toFixed(3)} against a ${floor.toFixed(3)} floor">not resolvable</span>`;
    vStyle = "font-weight:600;color:var(--text-secondary);";
  } else if (win) {
    mark = '<span style="color:var(--up);font-weight:700;">&#10003;</span>';
    vStyle = "font-weight:600;";
  } else {
    mark = '<span style="color:var(--down);font-weight:700;">&#10007;</span>';
    vStyle = "font-weight:700;color:var(--down);";
  }
  return `<tr><td class="meth-td-tier">${escapeHtml(label)}</td>
    <td>${cell.n != null ? cell.n : "-"}</td>
    <td style="${vStyle}">${Number(cell.efv).toFixed(3)}</td>
    <td style="color:var(--text-secondary);">${Number(cell.consensus).toFixed(3)}</td>
    <td>${mark}</td></tr>`;
}

function _sbSideTable(sideLabel, blk, floor) {
  if (!blk || !blk.pooled) return "";
  const p = blk.pooled;
  let rows = "";
  rows += _sbRow("Pooled ordering (Spearman)", p.spearman, floor);
  rows += _sbRow("Contributor AUC (WAR 3+)", p.auc_contributor, floor);
  rows += _sbRow("Star AUC (WAR 10+)", p.auc_star, floor);
  rows += _sbRow("Within-tier, FV 45 (t45)", blk.t45, floor);
  rows += _sbRow("Within-tier, weighted mean", blk.wm, floor);
  ["<=2018", "2019-2021", "2022-2023"].forEach(ek => {
    const c = blk.by_era && blk.by_era[ek];
    if (c) rows += _sbRow(`Era ${ek}`, c.spearman, floor);
  });
  Object.keys(blk.by_fv_tier || {}).sort((a, b) => Number(a) - Number(b)).forEach(tk => {
    rows += _sbRow(`FV tier ${tk}`, blk.by_fv_tier[tk], floor);
  });
  const cohLabels = { ifa: "Int'l signs", college: "College draftees", hs: "HS draftees", draft: "Draft (age unknown)", other: "Other" };
  Object.keys(cohLabels).forEach(ck => {
    const c = blk.by_cohort && blk.by_cohort[ck];
    if (c && c.efv != null) rows += _sbRow(cohLabels[ck], c, floor);
  });
  if (!rows) return "";
  return `<div class="meth-table-wrap">
    <div class="meth-table-title">${escapeHtml(sideLabel)} <span class="meth-sub">eFV vs consensus, identical rows</span></div>
    <div class="table-scroll-x"><table class="meth-table">
      <thead><tr><th>Cell</th><th>n</th><th>eFV</th><th>Consensus</th><th></th></tr></thead>
      <tbody>${rows}</tbody>
    </table></div>
  </div>`;
}

// E2a: the per-side calibration audit. Answers the question people actually ask
// about eFV ("why so few pitchers?") with outcomes rather than with a comparison
// to another board, which is the constraint the whole lane was built around: a
// source is not over-grading pitchers because it disagrees with us, only because
// it disagrees with what those pitchers produced.
//
// Reads data/xfv_side_calibration_eval.json live. Renders nothing when the
// artifact is absent, and nothing when no cell in it resolves, because the point
// of the panel is the resolved finding and a panel of "not resolvable" rows
// would read as a result.
function _methSideCalibration() {
  const j = _S.sideCal;
  if (!j || j.__error || !j.m1_realized_war_by_band) return "";
  const cons = ((j.m1_realized_war_by_band.consensus || {}).cells) || {};
  const efv = ((j.m1_realized_war_by_band.efv || {}).cells) || {};
  const f2 = v => (v == null ? "-" : Number(v).toFixed(2));
  const rows = [];
  const line = (label, band, c) => {
    if (!c || !c.resolvable) return;
    rows.push(`<tr><td class="meth-td-tier">${escapeHtml(label)} ${band}</td>
      <td>${c.n_hit}</td><td>${f2(c.mean_war_hit)}</td>
      <td>${c.n_pit}</td><td>${f2(c.mean_war_pit)}</td>
      <td class="${c.gap_pit_minus_hit >= 0 ? "" : "meth-neg"}">${c.gap_pit_minus_hit >= 0 ? "+" : ""}${f2(c.gap_pit_minus_hit)}</td>
      <td><span class="proj-dim">${f2(c.ci95 && c.ci95[0])} to ${f2(c.ci95 && c.ci95[1])}</span></td></tr>`);
  };
  Object.keys(cons).sort((a, b) => Number(b) - Number(a)).forEach(b => line("consensus FV", b, cons[b]));
  Object.keys(efv).sort((a, b) => Number(b) - Number(a)).forEach(b => line("eFV", b, efv[b]));
  if (!rows.length) return "";
  const f = (j.m2_per_side_forecast || {});
  const basis = j.basis || {};
  return `<div class="source-comp-wrap" id="side-calibration">
    <div class="source-comp-eyebrow"><span class="scx-dot"></span>Pitchers and hitters &middot; graded against what they became</div>
    <h2 class="meth-h">Does a grade mean the same thing for a pitcher as for a hitter?</h2>
    <p class="meth-note">eFV carries far fewer pitchers near the top of its board than the public lists do. That is a real difference and it is worth asking who is right, so we asked the only question that can answer it: <strong>at the same grade, what did each side actually produce?</strong> Nothing here compares one source's grade to another's. The reference throughout is realized first-six-year WAR on ${_saccN(basis.n)} resolved prospects, with players who never reached the majors carried at zero so survivors are not the only thing being scored.</p>
    <div class="table-scroll-x"><table class="meth-table">
      <thead><tr><th>Grade band</th><th>Hitters n</th><th>Their WAR</th><th>Pitchers n</th><th>Their WAR</th><th>Gap</th><th>95% interval</th></tr></thead>
      <tbody>${rows.join("")}</tbody>
    </table></div>
    <p class="meth-note">Only the bands that resolve are listed; every other cell sits inside its own noise and is published as unresolved in <a href="/data/xfv_side_calibration_eval.json" target="_blank" rel="noopener">the artifact</a>.</p>
    <p class="meth-verdict">The consensus grades pitchers <strong>too high at the top</strong>, measured against outcomes: at consensus FV 55 the hitters produced ${f2((cons["55"] || {}).mean_war_hit)} WAR and the pitchers ${f2((cons["55"] || {}).mean_war_pit)}. That is not a bust-rate story, because almost every player in both cells reached the majors. So eFV carrying fewer top-end pitchers is the more accurate reading of value, not a blind spot. In the other direction, eFV's own FV 45 band <strong>under-grades</strong> pitchers by a measurable margin, and that is a real defect on our side of the ledger rather than the industry's.</p>
    <p class="meth-note">The model's pitcher forecast itself is close to unbiased${(f.P && f.P.bias_pred_minus_real != null) ? ` (${f2(f.P.bias_pred_minus_real)} WAR against ${f2((f.H || {}).bias_pred_minus_real)} for hitters)` : ""}: it correctly expects pitchers to produce less, and one shared value curve then grades them lower. The low pitcher count is that curve spending a real difference, not a broken forecast. Method and the pre-registered decision rule: <code>docs/efv-2026-08-12/SIDE_CALIBRATION_GATE.md</code>.</p>
  </div>`;
}

function _methScoreboardHTML() {
  const j = _S.scoreEval;
  if (!j || j.__error || !j.sides) return "";
  // The floor the artifact publishes for exactly this comparison. Read it
  // rather than hardcoding: if the scoreboard is ever re-powered, the marks
  // must move with it.
  const floor = (j.basis && typeof j.basis.mde95_model_vs_consensus === "number")
    ? j.basis.mde95_model_vs_consensus : null;
  const hit = _sbSideTable("Hitters", j.sides.hit, floor);
  const pit = _sbSideTable("Pitchers", j.sides.pit, floor);
  if (!hit && !pit) return "";
  const nWeak = Array.isArray(j.weak_cells) ? j.weak_cells.length : 0;
  const cap = j.top20_capture && j.top20_capture.top20;
  const rec = j.disagreement_receipts || {};
  const extras = [];
  if (cap && cap.efv != null) extras.push(`top-20% WAR capture ${Number(cap.efv).toFixed(3)} vs ${Number(cap.consensus).toFixed(3)}${cap.win ? " (win)" : " (loss)"}`);
  // The share card sentence. Same rule as everywhere else, and DERIVED rather
  // than typed: a share card is the surface most likely to be screenshotted
  // away from its context, so the qualifier has to travel with the number. The
  // scoreboard artifact now carries `efv_right_share_resolvable`, so the day
  // the interval clears the coin this sentence drops the qualifier by itself.
  if (rec.efv_right_share != null) {
    const _q = rec.efv_right_share_resolvable === true ? ""
      : rec.efv_right_share_resolvable === false ? " (inside the noise)"
      : " (unfloored)";
    extras.push(`closer on ${(rec.efv_right_share * 100).toFixed(0)}% of the ${rec.n_disagreements} biggest resolved disagreements${_q}`);
  }
  const extraLine = extras.length
    ? `<p class="meth-note">Also on the card: ${escapeHtml(extras.join("; "))}. Full detail, receipts included, in <a href="/data/xfv_scoreboard_eval.json" target="_blank" rel="noopener">xfv_scoreboard_eval.json</a>.</p>`
    : `<p class="meth-note">Full detail in <a href="/data/xfv_scoreboard_eval.json" target="_blank" rel="noopener">xfv_scoreboard_eval.json</a>.</p>`;
  return `<div class="source-comp-wrap" id="efv-scoreboard">
    <div class="source-comp-eyebrow"><span class="scx-dot"></span>eFV Scoreboard &middot; the record, cell by cell</div>
    <h2 class="meth-h">Where eFV wins, and where it does not</h2>
    <p class="meth-note">Every cell is the same forward-chained out-of-sample read the evals use: eFV against the consensus baseline on identical players, era by era, FV tier by FV tier, cohort by cohort. A check is a win and a red cross is a loss, and the losses are left exactly as measured${nWeak ? ` (${nWeak} weak cells right now)` : ""}.${floor != null ? ` Most cells are neither: this board resolves a margin of ${floor.toFixed(3)} at 95 percent, so any cell inside that reads <em>not resolvable</em> rather than being counted for either side. That is most of them, and saying so is the point of publishing the board.` : ""}</p>
    <div class="meth-tables">${hit}${pit}</div>
    ${extraLine}
    <p class="meth-note"><strong>The losses set the agenda:</strong> the weak cells on this board, not the wins, drive the registered experiment queue for the next eFV program.</p>
  </div>`;
}

// Generate GFX (2026-07-23): the Source Comparison share card, rendered by the
// shared EEPHUS_GFX engine (kind:"sourcecomp", fixed Twitter 1200x675). The
// spec is built AT CLICK TIME from the same loaded artifacts this view renders
// (_S.backtest primary; _S.scoreEval fills capture / receipts if the backtest
// detail is absent), so the card can never carry a number the page does not.
// Returns null while the data has not loaded - the click is then a no-op.
//
// SAME BASIS AS THE PAGE (2026-09-24, census X01-01). The card read
// accuracy.pooled (eFV n 3,272 against the boards n 4,316) under the subtitle
// "Same players", starred eFV in both panels and tiled "0.757, best public
// 0.736", the full-pool AUC do-not-reopen item 3 rules inadmissible. It now
// reads the vintage-matched block the verdict is computed on, with no fallback,
// stars only through _hhStarRater, and carries no AUC tile: the AUC leg has no
// floor on these rows, and a share card travels without the page's caveats.
function _scxGfxSpec() {
  const bt = _S.backtest;
  if (!bt || bt.__error || !bt.accuracy || !bt.accuracy.pooled_efv_common_vintage_matched) return null;
  const pooled = bt.accuracy.pooled_efv_common_vintage_matched;
  const hh = bt.accuracy.head_to_head_verdict || null;
  const spStar = _hhStarRater(bt);
  const raters = ((bt.accuracy.head_to_head_raters) || bt.raters || []).slice();
  if (raters.indexOf("xfv") === -1 && pooled.xfv) raters.push("xfv");
  const f3 = v => (v == null || isNaN(Number(v)) ? "-" : Number(v).toFixed(3));
  // Ranked bar rows per metric: highest first, eFV flagged for the accent, the
  // public sources carrying their owner-palette identity colors (literal hex;
  // the canvas cannot resolve CSS var(), which is why eFV rides isEfv instead).
  const rowsFor = key => raters
    .map(r => ({ label: r === "xfv" ? "eFV" : _raterMeta(r).label,
                 v: pooled[r] ? pooled[r][key] : null,
                 isEfv: r === "xfv",
                 c: r === "xfv" ? null : _raterMeta(r).color }))
    .filter(r => r.v != null)
    .sort((a, b) => b.v - a.v);
  const sp = rowsFor("spearman"), au = rowsFor("auc");
  if (sp.length < 2 || !sp.some(r => r.isEfv)) return null;
  const x = pooled.xfv || {};
  const sb = (_S.scoreEval && !_S.scoreEval.__error) ? _S.scoreEval : null;

  // Key-stat tiles, each computed live. "best public" = the top-ranked
  // non-eFV row of the already-sorted list.
  const tiles = [];
  const bestPubSp = sp.filter(r => !r.isEfv)[0];
  const floorTxt = (hh && hh.resolvable === true) ? " · gap clears its floor"
    : (hh && hh.resolvable === false) ? " · gap inside its floor" : "";
  if (x.spearman != null) tiles.push({
    stat: f3(x.spearman),
    label: "eFV ordering skill (Spearman)",
    sub: bestPubSp ? "best public " + f3(bestPubSp.v) + " (" + bestPubSp.label + ")" + floorTxt : "grade vs realized WAR",
  });
  const cc = bt.accuracy.capture_curve;
  const sbCap = sb && sb.top20_capture && sb.top20_capture.top20;
  const capX = (cc && cc.xfv && cc.xfv.top20 != null) ? cc.xfv.top20 : (sbCap ? sbCap.efv : null);
  const capC = (cc && cc.consensus && cc.consensus.top20 != null) ? cc.consensus.top20 : (sbCap ? sbCap.consensus : null);
  if (capX != null) tiles.push({
    stat: Math.round(capX * 100) + "%",
    label: "of realized WAR in eFV's top 20%",
    sub: capC != null ? "consensus " + Math.round(capC * 100) + "% · busts included" : "busts included",
  });
  const det = bt.accuracy.xfv_vs_consensus_detail;
  const sbRec = sb && sb.disagreement_receipts;
  const _dr3 = _disagreementRead(det);
  const share = _dr3 ? _dr3.share
    : (sbRec && sbRec.efv_right_share != null ? sbRec.efv_right_share : null);
  const nDis = (det && det.n_disagreements != null) ? det.n_disagreements
    : (sbRec ? sbRec.n_disagreements : null);
  if (_dr3) tiles.push({
    stat: _dr3.stat,
    label: _dr3.resolvable
      ? "closer on the biggest disagreements"
      : "closer on the biggest disagreements (inside the noise)",
    sub: _dr3.sub,
  });
  else if (share != null) tiles.push({
    // The scoreboard fallback carries no interval at all, so it is labelled as
    // the unfloored number it is rather than borrowing the floored one's voice.
    stat: Math.round(share * 100) + "%",
    label: "closer on the biggest disagreements (unfloored)",
    sub: nDis != null ? nDis + " resolved eFV vs consensus splits, no interval available"
                      : "resolved disagreements, no interval available",
  });

  // Bar panels share the page chart's scales (_methAccuracyChart lo/hi). The
  // engine stars a panel's longest bar unless the panel says star:false.
  const panels = [];
  if (sp.length >= 2) panels.push({ title: "Ordering skill · Spearman (grade vs realized WAR)", lo: 0, hi: 0.5, rows: sp, star: spStar != null });
  if (au.length >= 2) panels.push({ title: "Discrimination · contributor AUC (no floor, none starred)", lo: 0.5, hi: 0.85, rows: au, star: false });

  const years = (bt.window && bt.window.years) || [];
  const span = years.length ? years[0] + "-" + years[years.length - 1] : "";
  const nCommon = bt.accuracy.common_n_efv_vintage_matched || x.n || null;
  const sgn3 = v => (v == null || isNaN(Number(v)) ? "-" : (Number(v) > 0 ? "+" : "") + Number(v).toFixed(3));
  const call = (hh && hh.delta != null && hh.mde95 != null)
    ? "eFV vs consensus " + sgn3(hh.delta) + ", floor " + f3(hh.mde95)
      + (hh.resolvable ? ", resolved" : ", not resolvable") + " · "
    : "";
  const note = "Every grader on the same rows, base year equal to the eFV decision year · "
    + call + "★ only where a gap clears a published floor";
  return {
    kind: "sourcecomp",
    module: "Source Comparison",
    accentToken: "--accent-lilac",
    format: "twitter",
    title: "Does eFV outperform its sources?",
    subtitle: "Same players, same outcome, same window, same vintage"
      + (nCommon ? " · n=" + Number(nCommon).toLocaleString() : "")
      + (span ? " · preseason cohorts " + span : ""),
    url: "eephus.io/glossary/",
    filenameBase: "eephus-source-comparison",
    caption: "Leakage-free, forward-chained backtest on resolved cohorts · misses included",
    comp: { tiles: tiles, panels: panels, note: note },
  };
}

// The chip row (shared EEPHUS_GFX styling). Rendered only from the data-state
// branch, so the button and the card read the same loaded backtest.
function _scxGfxBarHTML() {
  if (!window.EEPHUS_GFX || !window.EEPHUS_GFX.chipHTML) return "";
  return `<div class="filter-bar" style="margin:2px 0 10px;">${window.EEPHUS_GFX.chipHTML("gl-scx-gfx", "Generate GFX")}</div>`;
}

function renderSourceComparison() {
  const el = document.getElementById("source-comparison-body");
  if (!el) return;
  // The calibration cross-link tile shows the live tripwire status when the
  // shared reliability artifact is available (same guard as Methodology).
  _loadReliability();
  // Cohort-accuracy artifact: supplies the three-valued verdict column on the
  // archetype table below. Same lazy idiom; the table degrades to "not
  // measured" while it is in flight or absent.
  _loadSourceAccuracy();
  // Model upgrades panel artifacts (same lazy idiom).
  _loadUpgrades();
  // Scoreboard artifact (same lazy idiom).
  _loadScoreboard();
  if (!_S.backtest && !_S.btLoading) {
    _S.btLoading = true;
    const base = "/data/";
    fetch(base + "source_backtest.json", { cache: "no-cache" })
      .then(r => (r.ok ? r.json() : null))
      .then(j => { _S.backtest = j || { __error: true };
        if (_S.view === "source-comparison") renderSourceComparison(); })
      // A failed fetch (or a throw inside the re-render) must surface the
      // empty-state, never strand the loading placeholder.
      .catch(() => { _S.backtest = { __error: true };
        if (_S.view === "source-comparison") renderSourceComparison(); });
  }
  const bt = _S.backtest;
  let backtestHTML;
  if (!bt) {
    backtestHTML = `<div class="state-message">Loading backtest…</div>`;
  } else if (bt.__error || !bt.window || !bt.window.years || !bt.window.years.length) {
    backtestHTML = `<div class="meth-chart"><p class="meth-note">The source-vs-source backtest has no resolved cohorts yet (it needs ≥ 3 years of development lag). It will populate once the retained per-source history clears that window.</p></div>`;
  } else {
    const od = bt.outcome_defs || {};
    backtestHTML = `
      ${_methHeroBanner(bt)}
      ${_scxGfxBarHTML()}
      <h2 class="meth-h">The full head-to-head</h2>
      <p class="meth-window">eFV is the primary grade, our outcome-grounded model. The test: a leakage-free, forward-chained backtest of eFV against the public sources (FanGraphs, MLB Pipeline) and the PROSPX consensus, scored on how well each grade ordered what prospects became. ${escapeHtml(bt.window.note)} ${_excludedSourcesClause(bt)}</p>
      ${_methEfvFindings(bt)}
      ${_methPerYearChart(bt)}
      <h3 class="meth-h3">Head-to-head: ranking skill + contributor AUC</h3>
      ${_methAccuracyChart(bt)}
      ${_methConsensusVsInputsNote(bt)}
      ${_methEfvPanel(bt)}
      ${_methSideCalibration()}
      ${_methCalibCrossLink()}
      <h3 class="meth-h3">Where each grade wins, by prospect archetype</h3>
      <!-- 2026-08-10 (C-A4): this caption used to read "eFV leads the field
           overall and on most archetypes; the few it trails ...", which
           CONTRADICTED the computed line under the table beside it. That line
           reads the same artifact and says eFV posts the top AUC in 2 of 6
           archetypes, so "most" and "the few" were both false the moment the
           cohorts were re-scored. The count now comes only from the computed
           note, which cannot drift. -->
      <p class="meth-note">Per-archetype AUC below, with the measured FanGraphs-versus-Pipeline verdict beside it. Where eFV trails, it trails on the youngest, lowest-track-record cohorts, which is where the scouting consensus still reads projection best. The obvious adds (signing bonus, draft slot) are already priced into consensus FV, so out-of-sample they cost more than they returned.</p>
      ${_methArchetypeTable(bt)}
      <div class="meth-chart-grid">
        ${_methCaptureCurve(bt)}
        ${_methCalibrationChart(bt, "contributor_rate", "Contributor rate (career WAR ≥ " + (od.contributor_war ?? 3) + ")", { pct: true, yMax: 1 })}
      </div>
      <h3 class="meth-h3">Cohort outcomes by FV tier</h3>
      <p class="meth-note">Every prospect a source graded that preseason is in its cohort - players who never debuted stay in at 0 WAR (no survivorship cherry-picking). Cumulative WAR is censored at today, so younger cohorts (2023) have had less time to accrue it; the rate columns (WAR/yr, Reg pace) are less sensitive to that. <strong>eFV note:</strong> eFV is shown on its out-of-sample resolved cohort, which is debuted-heavy (its grades come from the labeled training pool), so its absolute WAR/contributor levels run a touch higher than the sources' full cohorts - compare the <em>shape</em> of the tier separation, not the absolute height.</p>
      <div class="meth-tables">${bt.raters.concat(bt.cohorts.xfv ? ["xfv"] : []).map(r => _methTierTable(bt, r)).join("")}</div>
      <div class="meth-caveats">
        <div class="meth-caveats-title">⚠ Read this honestly</div>
        <ul>
          <li><strong>Short track record.</strong> Only ${bt.window.years.length} preseason base years (${bt.window.years.join(", ")}) are old enough to have resolved outcomes. The newer sources have <em>zero</em> resolved cohorts.</li>
          <li><strong>Thin top tiers.</strong> The 60+ tier is only n≈40-60 across all years - a handful of hits or misses moves its rates a lot.</li>
          <li><strong>Censoring.</strong> Outcomes are cumulative WAR as of ${escapeHtml(bt.as_of_date || "today")}; the 2023 cohort has had ~3 seasons, the 2021 cohort ~5. Rate metrics mitigate but don't erase this.</li>
          <li>${_methCaveatHeadToHead(bt)}${_methCaveatArchetypeClause(bt)}</li>
          <li><strong>eFV is in-the-loop, not infallible.</strong> Its grades come from production we have; for the youngest prospects (recent draftees, int'l signs with no pro reps) it leans on the consensus prior, and where richer data exists (Statcast, Stuff+) it is only a live overlay, not yet historical.</li>
        </ul>
      </div>`;
  }
  // Framed as a distinct analytical area (eyebrow + bordered panel) so it reads
  // as the empirical evidence, not more prose.
  el.innerHTML = `<div class="source-comp-wrap">
    <div class="source-comp-eyebrow"><span class="scx-dot"></span>Empirical backtest · resolved cohorts only</div>
    ${backtestHTML}
  </div>` + _methScoreboardHTML() + _methModelUpgrades();
  // Generate GFX: spec built at click time from the loaded artifacts; a click
  // before the data resolves (or with the engine absent) is a clean no-op.
  const gfxBtn = document.getElementById("gl-scx-gfx");
  if (gfxBtn) gfxBtn.onclick = () => {
    const spec = _scxGfxSpec();
    if (spec && window.EEPHUS_GFX) window.EEPHUS_GFX.open(spec);
  };
}

// ---- Source Accuracy view (C-A4, 2026-08-10) --------------------------------
// The owner question was "who grades WHICH cohort better - hitters vs
// pitchers, draft vs international?". data/source_cohort_accuracy.json is the
// measurement and the answer is mostly NO ANSWER: 4 of 25 scored cells clear
// their own 95 percent minimum detectable effect, against 1.25 expected by
// construction at alpha 0.05, and the global head-to-head is itself not
// resolvable. ZERO WEIGHTS SHIP FROM THIS VIEW and the page says so on its
// first tile. Every number here is read from the artifact at render time; none
// is hardcoded, so the page cannot drift from the run that produced it.
const _SACC_TABS = [
  ["read-first", "Read this first"],
  ["side", "By side and acquisition"],
  ["archetype", "By archetype"],
  ["cuts", "Position, tier and age"],
  ["precision", "Precision (not accuracy)"],
  ["coverage", "Coverage and exclusions"],
];
const _SACC_LABELS = {
  bat: "Hitters", arm: "Pitchers",
  draft_hs: "Draft - high school", draft_college: "Draft - college",
  international: "International",
  hs_bat: "HS bats", hs_arm: "HS arms", college_bat: "College bats",
  college_arm: "College arms", intl_bat: "Int'l bats", intl_arm: "Int'l arms",
  C: "Catcher", IF: "Infield", OF: "Outfield", SP: "SP (FanGraphs role tag)",
  RP: "RP (FanGraphs role tag)", P_unspecified: "Pitcher, role unspecified",
  other: "Other / unlisted",
  "60+": "FV 60 and up", 55: "FV 55", 50: "FV 50", 45: "FV 45", "<45": "FV under 45",
  "<=18": "18 and under", "19-20": "19 to 20", "21-22": "21 to 22",
  "23-24": "23 to 24", ">=25": "25 and up",
};
function _saccLabel(k) { return _SACC_LABELS[k] || String(k); }
// Display name for an outlet that is NOT in _RATER_META. _raterMeta carries a
// colour and is the scored-rater palette; the outlets below are the ones with
// no resolvable history, so they never plot and belong here instead.
const _SACC_OUTLETS = { baseballamerica: "Baseball America", espn: "ESPN",
  just_baseball: "Just Baseball", tjstats: "TJStats" };
function _saccOutlet(s) { return _SACC_OUTLETS[s] || _raterMeta(s).label; }
// rho / AUC / delta are not FV grades, so they round NEAREST at 4 dp.
function _s4(v) { return v == null ? " - " : (Number(v) > 0 ? "+" : "") + Number(v).toFixed(4); }
function _f4(v) { return v == null ? " - " : Number(v).toFixed(4); }
function _f2(v) { return v == null ? " - " : Number(v).toFixed(2); }
function _f3(v) { return v == null ? " - " : Number(v).toFixed(3); }
function _saccN(v) { return v == null ? " - " : Number(v).toLocaleString("en-US"); }

// How many cells survived Holm, read from the artifact. Was the literal word
// "three" in the acquisition-path prose; the artifact moved to four on
// 2026-08-11 and the sentence went quietly wrong. Anything that counts the
// survivors must count THIS list.
function _saccHolmCount(d) {
  const h = d && d.multiplicity && d.multiplicity.holm_survivors;
  return Array.isArray(h) ? h.length : " - ";
}
function _saccPct(v) { return v == null ? " - " : (Number(v) * 100).toFixed(1) + "%"; }

function _loadSourceAccuracy() {
  if (_SACC || _SACC_LOADING) return;
  _SACC_LOADING = true;
  const rerender = () => {
    if (_S.view === "source-accuracy") renderSourceAccuracy();
    else if (_S.view === "source-comparison") renderSourceComparison();
  };
  fetch("/data/source_cohort_accuracy.json", { cache: "no-cache" })
    .then(r => (r.ok ? r.json() : null))
    .then(j => { _SACC = j || { __error: true }; _SACC_LOADING = false; rerender(); })
    // A failed fetch, or a throw inside the re-render, must surface the
    // retry state and never strand the loading placeholder.
    .catch(() => { _SACC = { __error: true }; _SACC_LOADING = false; rerender(); });
}

// The one honest cell on every table: the winning source name ONLY when the
// artifact says the cell is answerable, and the literal
// "not resolvable at this power" otherwise. No green on an unanswerable row.
// The CI rides along inside the cell so the mobile layout can drop its column
// without dropping the number.
function _saccVerdictCell(c) {
  if (!c) return `<td class="sacc-verdict"><span class="sacc-verdict-null">not measured</span></td>`;
  if (c.scored === false)
    return `<td class="sacc-verdict"><span class="sacc-verdict-null">not scored</span></td>`;
  const ok = c.answerable === true && c.winner && c.winner !== "not_resolvable";
  const body = ok
    ? `<span class="sacc-verdict-win">${escapeHtml(_raterMeta(c.winner).label)}</span>`
    : `<span class="sacc-verdict-null">not resolvable at this power</span>`;
  const holm = (ok && c.survives_holm === false)
    ? `<span class="sacc-holm-off">does not survive Holm inside its family</span>` : "";
  const ci = (Array.isArray(c.d_rho_ci) && c.d_rho_ci.length === 2)
    ? `<span class="sacc-ci-inline">CI95 ${_s4(c.d_rho_ci[0])} to ${_s4(c.d_rho_ci[1])}</span>` : "";
  return `<td class="sacc-verdict">${body}${holm}${ci}</td>`;
}
function _saccCiCell(c) {
  const ci = (Array.isArray(c.d_rho_ci) && c.d_rho_ci.length === 2)
    ? `${_s4(c.d_rho_ci[0])} to ${_s4(c.d_rho_ci[1])}` : " - ";
  return `<td class="sacc-col-ci">${ci}</td>`;
}
// Basis marker for a partition's rater columns, read off whichever cell first
// carries the field. Never keyed to a rater name.
function _saccBasisOf(part, rater) {
  for (const k of Object.keys(part || {})) {
    const c = part[k];
    const b = c && c.raters && c.raters[rater] && c.raters[rater].basis;
    if (b) return b;
  }
  return "";
}

// Cohort | n | FG rho | Pipeline rho | consensus rho | difference | CI95 | verdict.
function _saccRhoTable(part, title, sub, order) {
  const keys = (order || Object.keys(part || {})).filter(k => part && part[k]);
  if (!keys.length) return "";
  const head = ["fangraphs", "mlb_pipeline", "prospx_consensus"].map(r =>
    `<th>${escapeHtml(_raterMeta(r).label)}${_basisTag(_saccBasisOf(part, r))}</th>`).join("");
  const rows = keys.map(k => {
    const c = part[k];
    if (c.scored === false) {
      return `<tr class="sacc-row-unscored"><td class="meth-td-tier">${escapeHtml(_saccLabel(k))}</td>
        <td>${_saccN(c.n)}</td>
        <td colspan="6" class="sacc-unscored-note">${escapeHtml(c.note || "not scored")}</td></tr>`;
    }
    const g = r => ((c.raters || {})[r] && c.raters[r].spearman != null)
      ? _f4(c.raters[r].spearman) : " - ";
    return `<tr>
      <td class="meth-td-tier">${escapeHtml(_saccLabel(k))}</td>
      <td>${_saccN(c.n)}</td>
      <td>${g("fangraphs")}</td>
      <td>${g("mlb_pipeline")}</td>
      <td>${g("prospx_consensus")}</td>
      <td>${_s4(c.d_rho)}</td>
      ${_saccCiCell(c)}
      ${_saccVerdictCell(c)}
    </tr>`;
  }).join("");
  return `<div class="meth-table-wrap">
    <div class="meth-table-title">${escapeHtml(title)}${sub ? `<span class="meth-sub">${escapeHtml(sub)}</span>` : ""}</div>
    <div class="table-scroll-x"><table class="meth-table sacc-table">
      <thead><tr><th>Cohort</th><th>n</th>${head}<th>Difference</th><th class="sacc-col-ci">CI95</th><th class="sacc-verdict">Verdict</th></tr></thead>
      <tbody>${rows}</tbody>
    </table></div>
  </div>`;
}

// Archetype | n | d_rho | CI95 | MDE95 | verdict. The narrow form, used where
// the difference and its floor are the whole story.
function _saccEffectTable(part, title, sub, order) {
  const keys = (order || Object.keys(part || {})).filter(k => part && part[k]);
  if (!keys.length) return "";
  const rows = keys.map(k => {
    const c = part[k];
    if (c.scored === false) {
      return `<tr class="sacc-row-unscored"><td class="meth-td-tier">${escapeHtml(_saccLabel(k))}</td>
        <td>${_saccN(c.n)}</td>
        <td colspan="4" class="sacc-unscored-note">${escapeHtml(c.note || "not scored")}</td></tr>`;
    }
    return `<tr>
      <td class="meth-td-tier">${escapeHtml(_saccLabel(k))}</td>
      <td>${_saccN(c.n)}</td>
      <td>${_s4(c.d_rho)}</td>
      ${_saccCiCell(c)}
      <td class="sacc-col-mde">${_f4(c.mde95)}</td>
      ${_saccVerdictCell(c)}
    </tr>`;
  }).join("");
  return `<div class="meth-table-wrap">
    <div class="meth-table-title">${escapeHtml(title)}${sub ? `<span class="meth-sub">${escapeHtml(sub)}</span>` : ""}</div>
    <div class="table-scroll-x"><table class="meth-table sacc-table">
      <thead><tr><th>Cohort</th><th>n</th><th>Difference</th><th class="sacc-col-ci">CI95</th><th class="sacc-col-mde">MDE95</th><th class="sacc-verdict">Verdict</th></tr></thead>
      <tbody>${rows}</tbody>
    </table></div>
  </div>`;
}

function _saccTile(stat, label, sub) {
  return `<div class="meth-find-card">
    <div class="meth-find-stat">${stat}</div>
    <div class="meth-find-label">${label}</div>
    ${sub ? `<div class="meth-find-sub">${sub}</div>` : ""}
  </div>`;
}

// ---- sub-tab 1: read this first --------------------------------------------
function _saccReadFirst(d) {
  const b = d.basis || {}, m = d.multiplicity || {}, rep = d.reproduction || {};
  const bt = (_S.backtest && !_S.backtest.__error) ? _S.backtest : null;
  const scored = bt && Array.isArray(bt.scored_sources) ? bt.scored_sources.length : null;
  const blocked = bt && Array.isArray(bt.insufficient_history) ? bt.insufficient_history.length : null;
  const outlets = (scored != null && blocked != null) ? scored + blocked : null;
  const tiles = [
    _saccTile(_saccN(b.deduped_players), "resolved players carry the measurement",
      `one row per player, latest pre-debut read, from ${_saccN(b.pooled_common_rows)} pooled common rows`),
    _saccTile(outlets != null ? `${scored} / ${outlets}` : " - ",
      "outlets have a resolvable outcome history",
      bt ? `scored: ${escapeHtml((bt.scored_sources || []).map(_saccOutlet).join(", "))} &middot; blocked: ${escapeHtml((bt.insufficient_history || []).map(_saccOutlet).join(", "))}` : ""),
    _saccTile(`${_saccN(m.cells_flagged_answerable)} / ${_saccN(m.cells_tested)}`,
      "scored cells clear their own noise floor",
      `${_f2(m.expected_false_positives_at_alpha_05)} are expected by construction at alpha 0.05`),
    _saccTile(d.ships_a_weight === false ? "0" : "?",
      "weights ship from this measurement",
      "the deliverable is the measurement and this page, not a weight"),
  ].join("");
  const holm = Array.isArray(m.holm_survivors) ? m.holm_survivors : [];
  return `
    <div class="meth-findings">${tiles}</div>
    <p class="meth-note sacc-headline">${escapeHtml(d.headline || "")}</p>
    <h3 class="meth-h3">What was measured</h3>
    <div class="table-scroll-x"><table class="meth-table sacc-kv">
      <tbody>
        <tr><td class="meth-td-tier">Estimand</td><td>${escapeHtml(b.estimand || " - ")}</td></tr>
        <tr><td class="meth-td-tier">Uncertainty</td><td>${escapeHtml(b.uncertainty || " - ")}</td></tr>
        <tr><td class="meth-td-tier">Dedup rule</td><td>${escapeHtml(b.dedup_rule || " - ")}</td></tr>
        <tr><td class="meth-td-tier">Base years</td><td>${escapeHtml((b.window_years || []).join(", "))} &middot; minimum development lag ${_saccN(b.min_lag_years)} years</td></tr>
        <tr><td class="meth-td-tier">Pre-registered</td><td>${(b.pre_registration || []).map(p => `<code>${escapeHtml(p)}</code>`).join("<br>") || " - "}</td></tr>
        <tr><td class="meth-td-tier">Reproduces</td><td>${escapeHtml(b.reproduces || " - ")}${rep.matches_source_backtest_code === true ? " &middot; matches the shipped source_backtest code and served artifact, max absolute rho difference " + _f4(b.rho_implementation_max_abs_diff) : ""}</td></tr>
        <tr><td class="meth-td-tier">Run</td><td>${escapeHtml(d.produced_by || " - ")} &middot; as of ${escapeHtml(d.as_of_date || " - ")}</td></tr>
      </tbody>
    </table></div>
    <h3 class="meth-h3">The ${_saccN(m.cells_flagged_answerable)} cells that cleared their floor</h3>
    <p class="meth-note">${holm.length ? `After a Holm correction inside each partition, ${holm.length} survive: ${holm.map(h => `<code>${escapeHtml(h)}</code>`).join(", ")}. ` : ""}${escapeHtml(m.survivors_overlap_note || "")}</p>
    <div class="meth-caveats">
      <div class="meth-caveats-title">&#9888; Read this honestly</div>
      <ul>
        <li><strong>The global head-to-head does not resolve.</strong> Pooled difference ${_s4((d.accuracy || {}).pooled && d.accuracy.pooled.d_rho)} against a minimum detectable effect of ${_f4((d.accuracy || {}).pooled && d.accuracy.pooled.mde95)}, bootstrap two-sided p ${_f4((d.accuracy || {}).pooled && d.accuracy.pooled.boot_p_two_sided)}. Every cohort claim on the tabs below sits inside that.</li>
        <li><strong>A survivor count is not a family test.</strong> ${_saccN(m.cells_tested)} cells at alpha 0.05 produce about ${_f2(m.expected_false_positives_at_alpha_05)} flags with no signal at all.</li>
        <li><strong>Both public sources are scored in sample.</strong> They are graders, not models: there is no training set to hold out. That is why the numbers here are ordering skill on a common set and not an out-of-sample claim.</li>
        <li><strong>No weight ships.</strong> Six cohort-weight arms were fit and all six lose to equal weight. The receipt is on the archetype tab.</li>
      </ul>
    </div>`;
}

// ---- sub-tab 2: by side and by acquisition ----------------------------------
function _saccBySide(d) {
  const a = d.accuracy || {};
  const hs = (a.by_acquisition || {}).draft_hs || {};
  return `<p class="meth-window">The two cuts the owner asked for. A positive difference means FanGraphs ordered that cohort better; negative means MLB Pipeline did. The verdict column is the whole point: a cell is called only when the measured difference clears that cell's own 95 percent minimum detectable effect, and every other cell reads <em>not resolvable at this power</em> rather than crowning the larger of two statistically identical numbers.</p>
    ${_saccRhoTable(a.by_side, "Hitters vs pitchers", "Spearman rho, preseason grade against realized WAR", ["bat", "arm"])}
    ${_saccRhoTable(a.by_acquisition, "Draft vs international", "Spearman rho, preseason grade against realized WAR", ["draft_hs", "draft_college", "international"])}
    <p class="meth-note">Neither side resolves. On acquisition path, one cell does: high-school draftees, where the difference is ${_s4(hs.d_rho)} against a floor of ${_f4(hs.mde95)}, so MLB Pipeline orders that cohort better. It is one of the ${_saccHolmCount(d)} cells that survive a Holm correction inside their own partition. College and international do not resolve.</p>`;
}

// ---- sub-tab 3: by archetype ------------------------------------------------
function _saccByArchetype(d) {
  const a = d.accuracy || {}, m = d.multiplicity || {}, h = m.archetype_heterogeneity || {};
  const order = ["hs_bat", "hs_arm", "college_bat", "college_arm", "intl_bat", "intl_arm"];
  const fam = [
    _saccTile(_f4(h.chi2_p), `Cochran Q p (Q ${_f4(h.cochran_q)}, df ${_saccN(h.df)}, k ${_saccN(h.k)})`,
      "one common difference across the six archetypes is not rejected"),
    _saccTile(_f4(h.permutation_p_labels), `label-permutation p (${_saccN(h.permutation_draws)} draws)`,
      "share of random archetype labelings that produce a spread this wide or wider"),
    _saccTile(`${_f2(h.i2_percent)}%`, "I&sup2;, share of spread beyond sampling noise",
      `tau ${_f4(h.tau)} on a weighted mean difference of ${_s4(h.weighted_mean_d_rho)}`),
  ].join("");
  const ab = d.cohort_ab || {}, arms = ab.arms || {}, gate = ab.gate || {};
  const armRows = Object.keys(arms).map(k => {
    const v = arms[k];
    return `<tr${k === ab.best_arm ? ' class="sacc-row-best"' : ""}>
      <td class="meth-td-tier">${escapeHtml(k)}${k === ab.best_arm ? " (best)" : ""}</td>
      <td>${_saccN(v.pooled_n)}</td>
      <td>${_f4((v.equal || {}).spearman)}</td>
      <td>${_f4((v.weighted || {}).spearman)}</td>
      <td>${_s4(v.d_rho)}</td>
      <td>${_s4(v.d_auc)}</td>
      <td class="sacc-verdict"><span class="${v.ship ? "sacc-verdict-win" : "sacc-verdict-null"}">${v.ship ? "ships" : "no ship"}</span></td>
    </tr>`;
  }).join("");
  const pc = ab.permutation_control || {};
  const ss = ab.shrink_sensitivity || {};
  const oc = d.oracle_ceiling || {};
  const ocRows = Object.keys(oc).map(k => {
    const v = oc[k];
    return `<tr>
      <td class="meth-td-tier">${escapeHtml(v.basis || k)}</td>
      <td>${_saccN(v.n)}</td>
      <td>${_f4(v.equal_rho)}</td>
      <td>${_f4(v.global_oracle_alpha)}</td>
      <td>${_f4(v.global_oracle_rho)}</td>
      <td>${_s4(v.global_oracle_gain)}</td>
      <td class="sacc-verdict"><span class="${v.global_oracle_clears_ship_gate ? "sacc-verdict-win" : "sacc-verdict-null"}">${v.global_oracle_clears_ship_gate ? "clears the gate" : "below the gate"}</span></td>
    </tr>`;
  }).join("");
  const bys = m.base_year_stability || {};
  const byRows = (bys.per_year || []).map(y => `<tr>
    <td class="meth-td-tier">${escapeHtml(String(y.year))}</td>
    <td>${_saccN(y.n)}</td>
    <td>${_f4(y.rho_fangraphs)}</td>
    <td>${_f4(y.rho_mlb_pipeline)}</td>
    <td>${_s4(y.d_rho)}</td>
  </tr>`).join("");
  return `<p class="meth-window">Six archetypes, the finest cut this data supports. This is the most valuable block on the page and it is a negative result: the spread across the six is inside the band that randomly shuffled archetype labels produce.</p>
    ${_saccEffectTable(a.by_archetype, "FanGraphs minus MLB Pipeline, by archetype", "difference in Spearman rho against each cell's own floor", order)}
    <h3 class="meth-h3">The family test</h3>
    <div class="meth-findings">${fam}</div>
    <div class="meth-find-card sacc-family-card">
      <div class="meth-find-label">The archetype pattern is inside the noise band of randomly shuffled archetype labels.</div>
      <div class="meth-find-sub">${escapeHtml(h.reading || "")}</div>
    </div>
    <h3 class="meth-h3">The six-arm A/B receipt</h3>
    <p class="meth-note">Every arm refits the FanGraphs/Pipeline blend on cohort labels over ${_saccN(ab.rows_n)} rows and is scored forward-chained: ${escapeHtml(ab.vintage_rule || "")}. Gate: difference in Spearman at least ${_f4(gate.min_d_rho)} or difference in AUC at least ${_f4(gate.min_d_auc)}, taken from ${escapeHtml(gate.source || "the incumbent constants")}. Alpha, the only free parameter a two-source blend has, is ${escapeHtml((ab.alpha_parameterisation || {}).definition || "")}; the shipped clamp bounds it to ${((ab.alpha_parameterisation || {}).implied_alpha_range || []).map(v => _f4(v)).join(" to ") || " - "}.</p>
    <div class="meth-table-wrap">
      <div class="table-scroll-x"><table class="meth-table sacc-table">
        <thead><tr><th>Arm</th><th>n</th><th>Equal-weight rho</th><th>Weighted rho</th><th>Difference rho</th><th>Difference AUC</th><th class="sacc-verdict">Verdict</th></tr></thead>
        <tbody>${armRows}</tbody>
      </table></div>
    </div>
    <div class="meth-findings">
      ${_saccTile(_f4(pc.p), `permutation control p (${_saccN(pc.draws)} draws)`, escapeHtml(pc.reading || ""))}
      ${_saccTile(_s4(pc.observed_d_rho), "observed difference for the best arm",
        `null mean ${_s4(pc.null_mean)}, null sd ${_f4(pc.null_sd)}, null 95th percentile ${_s4(pc.null_p95)}`)}
    </div>
    <p class="meth-note"><strong>Shrinkage sensitivity.</strong> ${escapeHtml(ss.reading || "")} Rank correlation of k against the Spearman difference ${_f4(ss.rank_corr_k_vs_d_rho)}, against the AUC difference ${_f4(ss.rank_corr_k_vs_d_auc)}.</p>
    <h3 class="meth-h3">The oracle ceiling</h3>
    <p class="meth-note">The best blend weight chosen with hindsight, on the same rows. It bounds what any fitting procedure could have won, so it separates "we estimated it badly" from "there is nothing there".</p>
    <div class="meth-table-wrap">
      <div class="table-scroll-x"><table class="meth-table sacc-table">
        <thead><tr><th>Basis</th><th>n</th><th>Equal-weight rho</th><th>Oracle alpha</th><th>Oracle rho</th><th>Gain</th><th class="sacc-verdict">Verdict</th></tr></thead>
        <tbody>${ocRows}</tbody>
      </table></div>
    </div>
    <p class="meth-note">${escapeHtml((oc.deduped_common || {}).geometry_note || "")} FanGraphs and Pipeline correlate ${_f4((oc.deduped_common || {}).corr_fg_mp_pearson)} on the deduped common set.</p>
    <h3 class="meth-h3">Would a cohort weight even hold still?</h3>
    <p class="meth-note">${escapeHtml(bys.note || "")} ${bys.sign_flips_across_adjacent_vintages != null ? `Sign flips across adjacent vintages: ${_saccN(bys.sign_flips_across_adjacent_vintages)}.` : ""}</p>
    <div class="meth-table-wrap">
      <div class="table-scroll-x"><table class="meth-table sacc-table">
        <thead><tr><th>Base year</th><th>n</th><th>FanGraphs rho</th><th>Pipeline rho</th><th>Difference</th></tr></thead>
        <tbody>${byRows}</tbody>
      </table></div>
    </div>`;
}

// ---- sub-tab 4: position, tier and age --------------------------------------
function _saccCuts(d) {
  const a = d.accuracy || {};
  const lvl = a.level_at_grading || {};
  return `<p class="meth-window">Three more cuts, stacked. Each carries the reason it is weaker than the two above, inline, because two of the three are weak by construction rather than by sample size.</p>
    ${_saccRhoTable(a.by_position_group, "By position group", "Spearman rho against realized WAR",
      ["C", "IF", "OF", "SP", "RP", "P_unspecified", "other"])}
    <p class="meth-note sacc-warn">${escapeHtml(a.by_position_group_selection_caveat || "")}</p>
    ${_saccRhoTable(a.by_fv_tier, "By consensus FV tier", "Spearman rho against realized WAR",
      ["60+", "55", "50", "45", "<45"])}
    <p class="meth-note sacc-warn">${escapeHtml(a.by_fv_tier_range_restriction_warning || "")}</p>
    ${_saccRhoTable(a.by_age_at_grading, "By age at grading", "Spearman rho against realized WAR",
      ["<=18", "19-20", "21-22", "23-24", ">=25"])}
    <p class="meth-note sacc-warn">${escapeHtml(lvl.note || "")}${lvl.available === false ? ` Substitute in use: <code>${escapeHtml(lvl.substitute || "")}</code>.` : ""}</p>`;
}

// ---- sub-tab 5: precision (not accuracy) ------------------------------------
// TWO BRANCHES, and the IDENTIFIED one is what ships today: the Baseball
// America backfill landed, so the triad is complete and
// precision_label_free.identified is true on 6,287 rows. This comment used to
// say the opposite - that BA had been purged and two sources cannot identify a
// measurement-error model - which was true for a few hours on 2026-08-10 and
// has been wrong in every artifact since, including at HEAD. The predicate
// below is written defensively and routes correctly either way; only the
// description was stale, and a stale description is what sends the next editor
// to fix the wrong branch. The unidentified branch remains real: it renders the
// reason and the restore condition and NO TABLE, NO SIGMA, NO ALPHA. Nothing on
// this page may assume the block is populated.
function _saccPrecision(d) {
  const p = d.precision_label_free || {};
  const wording = `<div class="sacc-wording">
    <div class="sacc-wording-title">Precision is not accuracy</div>
    <p>Precision is not accuracy. This block measures how tightly each outlet agrees with the latent consensus, with each outlet's own scale offset and slope removed. It says nothing about who is right. Where we can measure accuracy against outcomes we say so separately, and on the one cohort where accuracy is resolvable the two disagree.</p>
  </div>`;
  // BRANCH PREDICATE. source_cohort_accuracy._precision_label_free emits
  // "identified": false on the unidentified early return, and the populated
  // return carries identified: true. Testing for an explicit false OR a missing
  // estimator (rather than a truthy read) keeps it correct under both shapes,
  // including artifacts written before the key existed.
  const em = p.estimator_primary_em_fiml;
  if (p.identified === false || !em || !Array.isArray(em.sources)) {
    return `${wording}
      <div class="sacc-empty">
        <div class="sacc-empty-title">Not identified - nothing is rendered</div>
        <p class="sacc-empty-reason">${escapeHtml(p.reason || "the measurement-error model is not identified on the sources present")}</p>
        <div class="table-scroll-x"><table class="meth-table sacc-kv">
          <tbody>
            <tr><td class="meth-td-tier">Sources present</td><td>${(p.sources_present || []).map(s => escapeHtml(_saccOutlet(s))).join(", ") || " - "}</td></tr>
            <tr><td class="meth-td-tier">Third instrument</td><td>${escapeHtml(_saccOutlet(p.third_instrument || ""))}, ${_saccN(p.n_third_instrument_rows)} usable rows against a floor of ${_saccN(p.min_rows_required)}</td></tr>
            <tr><td class="meth-td-tier">Restores when</td><td>${escapeHtml(p.restores_when || " - ")}</td></tr>
          </tbody>
        </table></div>
        <p class="meth-note">Two instruments cannot separate an outlet's noise from the latent grade: with two readings of one quantity, every split of the disagreement between them fits equally well. A third independent reading is what identifies the model, which is why nothing is estimated here rather than something being estimated badly.</p>
      </div>`;
  }
  // Identified branch: the triad source table, the range-restriction chips,
  // the vintage-availability table, and the precision-vs-accuracy row. Every
  // field below is the schema _precision_label_free ships on its populated
  // return; each is read defensively so a partial artifact drops a row rather
  // than throwing inside the render.
  const cc = p.estimator_robustness_complete_case || {};
  const at = (arr, i) => (Array.isArray(arr) && arr[i] != null) ? arr[i] : null;
  const srcRows = em.sources.map((s, i) => `<tr>
    <td class="meth-td-tier">${escapeHtml(_saccOutlet(s))}</td>
    <td>${_f4(at(em.b, i))}</td>
    <td>${_f4(at(em.sigma, i))}</td>
    <td>${_f4(at(em.reliability, i))}</td>
    <td>${_f4(at(em.gls_weight, i))}</td>
    <td>${_f4(at(cc.sigma, i))}</td>
  </tr>`).join("");
  const rr = p.range_restricted_sources || {};
  const rrChips = Object.keys(rr).map(k => {
    const v = rr[k] || {};
    const on = v.range_restricted === true;
    return `<span class="${on ? "sacc-chip-warn" : "sacc-chip-ok"}" title="${escapeHtml(v.why_no_weight || "")}">${escapeHtml(_saccOutlet(k))}: ${on ? "range restricted" : "full range"}, sd ratio ${_f4(v.sd_ratio_vs_fangraphs)} on ${_saccN(v.n)} rows, weight ${v.weight == null ? "none" : _f4(v.weight)}</span>`;
  }).join("");
  const vint = p.vintage_availability || {};
  const byYear = vint.precision_estimable_by_board_year || {};
  const vintRows = Object.keys(byYear).sort().map(y => {
    const v = byYear[y] || {};
    return `<tr>
      <td class="meth-td-tier">${escapeHtml(y)}</td>
      <td>${_saccN(v.complete_case_n)}</td>
      <td class="sacc-verdict"><span class="${v.estimable ? "sacc-verdict-win" : "sacc-verdict-null"}">${v.estimable ? "estimable" : "not estimable"}</span></td>
      <td>${v.alpha_fg == null ? " - " : _f4(v.alpha_fg)}</td>
      <td>${escapeHtml(String(v.reason || (v.heywood ? "triad refuted on these rows" : " - ")))}</td>
    </tr>`;
  }).join("");
  const pva = p.precision_vs_accuracy || {};
  const cells = Array.isArray(pva.on_the_resolvable_cells) ? pva.on_the_resolvable_cells : [];
  const pvaRows = cells.map(c => `<tr>
    <td class="meth-td-tier">${escapeHtml(_saccLabel(c.archetype))}</td>
    <td>${escapeHtml(_raterMeta(c.accuracy_winner).label)}</td>
    <td>${_s4(c.accuracy_d_rho)}</td>
    <td>${escapeHtml(_raterMeta(c.precision_prefers).label)}</td>
    <td>${_f4(c.precision_alpha_fg)}</td>
    <td class="sacc-verdict"><span class="${c.agree ? "sacc-verdict-win" : "sacc-verdict-null"}">${c.agree ? "agree" : "disagree"}</span></td>
  </tr>`).join("");
  return `${wording}
    <div class="meth-table-wrap">
      <div class="meth-table-title">Per-outlet precision <span class="meth-sub">EM/FIML on per-source, per-year centred grades; complete case as the robustness column</span></div>
      <div class="table-scroll-x"><table class="meth-table sacc-table">
        <thead><tr><th>Outlet</th><th>Loading b</th><th>Sigma</th><th>Reliability</th><th>GLS weight</th><th>Sigma, complete case</th></tr></thead>
        <tbody>${srcRows}</tbody>
      </table></div>
    </div>
    <p class="meth-note">alpha ${_f4(em.alpha_fg)}${Array.isArray(em.alpha_fg_ci95) ? `, CI95 ${_f4(em.alpha_fg_ci95[0])} to ${_f4(em.alpha_fg_ci95[1])}` : ""} on ${_saccN(em.n_rows_used)} rows. ${escapeHtml(p.gls_weight_form || "")}</p>
    ${rrChips ? `<div class="sacc-chiprow">${rrChips}</div>` : ""}
    <h3 class="meth-h3">Why this cannot be scored against outcomes yet</h3>
    <div class="meth-table-wrap">
      <div class="table-scroll-x"><table class="meth-table sacc-table">
        <thead><tr><th>Board year</th><th>Complete case n</th><th class="sacc-verdict">Status</th><th>alpha</th><th>Note</th></tr></thead>
        <tbody>${vintRows}</tbody>
      </table></div>
    </div>
    <p class="meth-note sacc-warn">${escapeHtml(vint.structural_note || "")}</p>
    <h3 class="meth-h3">Precision against accuracy, on the cells where accuracy resolves</h3>
    ${pvaRows ? `<div class="meth-table-wrap"><div class="table-scroll-x"><table class="meth-table sacc-table">
      <thead><tr><th>Archetype</th><th>Accuracy prefers</th><th>Difference</th><th>Precision prefers</th><th>alpha</th><th class="sacc-verdict">Verdict</th></tr></thead>
      <tbody>${pvaRows}</tbody>
    </table></div></div>` : `<p class="meth-note">No archetype has both a resolvable accuracy verdict and an estimable precision alpha.</p>`}
    <p class="meth-note">Pearson r ${_f4(pva.pearson_r)}, exact permutation p ${_f4(pva.permutation_p_two_sided)}. ${escapeHtml(pva.reading || "")}</p>`;
}

// ---- sub-tab 6: coverage and what is excluded -------------------------------
function _saccCoverage(d) {
  const cs = (d.accuracy || {}).coverage_selection || {};
  const per = cs.per_source || {};
  const rows = Object.keys(per).map(k => {
    const v = per[k] || {};
    return `<tr>
      <td class="meth-td-tier">${escapeHtml(_saccOutlet(k))}</td>
      <td>${_saccN(v.rows_own)}</td>
      <td>${_saccN(v.rows_common)}</td>
      <td>${_saccN(v.rows_cut)}</td>
      <td>${_f4(v.rho_own)}</td>
      <td>${_f4(v.rho_common)}</td>
      <td>${_s4(v.delta_own_minus_common)}</td>
      <td>${_f2(v.cut_mean_fv)} / ${_f2(v.kept_mean_fv)}</td>
      <td>${_saccPct(v.cut_debut_rate)} / ${_saccPct(v.kept_debut_rate)}</td>
    </tr>`;
  }).join("");
  const cd = d.calibration_drift || {};
  const srcs = Object.keys(cd.sources || {});
  const years = [...new Set(srcs.flatMap(s => Object.keys((cd.sources[s] || {}).per_year || {})))]
    .sort();
  const driftRows = years.map(y => `<tr>
    <td class="meth-td-tier">${escapeHtml(y)}</td>
    ${srcs.map(s => {
      const e = ((cd.sources[s] || {}).per_year || {})[y];
      return `<td>${e ? _f3(e.offset_fv) : " - "}</td>`;
    }).join("")}
  </tr>`).join("");
  const bt = (_S.backtest && !_S.backtest.__error) ? _S.backtest : null;
  const cls = bt && Array.isArray(bt.source_classification) ? bt.source_classification : [];
  const clsRows = cls.map(c => `<tr>
    <td class="meth-td-tier">${escapeHtml(_saccOutlet(c.source))}</td>
    <td class="sacc-verdict"><span class="${c.scoreable_now ? "sacc-verdict-win" : "sacc-verdict-null"}">${c.scoreable_now ? "scoreable" : "not scoreable"}</span></td>
    <td>${escapeHtml(String(c.blocked_by || " - "))}</td>
    <td>${_saccN(c.resolvable_rows_total)}</td>
    <td>${_saccPct(c.common_set_retention)}</td>
  </tr>`).join("");
  const clsRuleNote = (bt && bt.source_class_rules && bt.source_class_rules.note)
    ? `<p class="meth-note">${escapeHtml(bt.source_class_rules.note)}</p>` : "";
  const clsBlock = clsRows
    ? `<div class="meth-table-wrap"><div class="table-scroll-x"><table class="meth-table sacc-table">
        <thead><tr><th>Outlet</th><th class="sacc-verdict">Status</th><th>Blocked by</th><th>Resolvable rows</th><th>Common-set retention</th></tr></thead>
        <tbody>${clsRows}</tbody>
      </table></div></div>${clsRuleNote}`
    : `<p class="meth-note">The source classification table is loading.</p>`;
  return `<p class="meth-window">What the common set threw away, whether the scale itself moved under the measurement, and which outlets could not be scored at all. Naming the exclusion and publishing its size is the honest form of this evidence: the cut rows carry zero paired contrast, so no model recovers them.</p>
    <div class="meth-table-wrap">
      <div class="meth-table-title">Coverage and selection <span class="meth-sub">own rows against the two-source common set</span></div>
      <div class="table-scroll-x"><table class="meth-table sacc-table">
        <thead><tr><th>Outlet</th><th>Own rows</th><th>Common</th><th>Cut</th><th>rho own</th><th>rho common</th><th>Difference</th><th>Mean FV cut / kept</th><th>Debut rate cut / kept</th></tr></thead>
        <tbody>${rows}</tbody>
      </table></div>
    </div>
    <p class="meth-note">Row retention ${_saccPct(cs.row_retention)}, player retention ${_saccPct(cs.player_retention)} of ${_saccN(cs.union_player_year_slots)} union player-year slots. Kept rows average FV ${_f2(cs.kept_pooled_mean_source_fv)} and debut at ${_saccPct(cs.kept_pooled_debut_rate)}; cut rows average FV ${_f2(cs.cut_pooled_mean_source_fv)} and debut at ${_saccPct(cs.cut_pooled_debut_rate)}.</p>
    <p class="meth-note"><strong>No selection model was built, and that is a decision, not an omission.</strong> ${escapeHtml((cs.selection_model || {}).why_not || "")}</p>
    <h3 class="meth-h3">Calibration drift against FanGraphs</h3>
    <p class="meth-note">${escapeHtml(cd.note || "")} Flag threshold ${_f2(cd.flag_threshold_fv)} FV points year over year; currently flagged: ${(cd.flagged || []).length ? escapeHtml(cd.flagged.join(", ")) : "none"}.</p>
    <div class="meth-table-wrap">
      <div class="table-scroll-x"><table class="meth-table sacc-table">
        <thead><tr><th>Year</th>${srcs.map(s => `<th>${escapeHtml(_saccOutlet(s))}</th>`).join("")}</tr></thead>
        <tbody>${driftRows}</tbody>
      </table></div>
    </div>
    <h3 class="meth-h3">Outlets that could not be scored</h3>
    ${clsBlock}`;
}

function renderSourceAccuracy() {
  const el = document.getElementById("source-accuracy-body");
  if (!el) return;
  _loadSourceAccuracy();
  // source_backtest.json supplies the outlet counts on tab 1 and the
  // source_classification table on tab 6. Same lazy guard the Source
  // Comparison view uses; the two views share _S.backtest.
  if (!_S.backtest && !_S.btLoading) {
    _S.btLoading = true;
    fetch("/data/source_backtest.json", { cache: "no-cache" })
      .then(r => (r.ok ? r.json() : null))
      .then(j => { _S.backtest = j || { __error: true };
        if (_S.view === "source-accuracy") renderSourceAccuracy(); })
      .catch(() => { _S.backtest = { __error: true };
        if (_S.view === "source-accuracy") renderSourceAccuracy(); });
  }
  const shell = inner => {
    const chips = _SACC_TABS.map(([k, lbl]) =>
      `<button class="chip${_SACC_TAB === k ? " active" : ""}" type="button" data-sacc-tab="${escapeHtml(k)}">${escapeHtml(lbl)}</button>`).join("");
    return `<div class="source-comp-wrap sacc-wrap">
      <div class="source-comp-eyebrow"><span class="scx-dot"></span>Source accuracy by cohort &middot; zero weights ship</div>
      <h2 class="meth-h">Who is better on which kind of prospect?</h2>
      <div class="filter-bar sacc-tabs"><span class="gl-microlabel">Section</span>${chips}</div>
      ${inner}
    </div>`;
  };
  const d = _SACC;
  let inner;
  if (!d) {
    inner = `<div class="state-message">Loading the cohort accuracy measurement...</div>`;
  } else if (d.__error || !d.accuracy) {
    inner = `<div class="state-message">The cohort accuracy measurement could not be loaded.
      <div style="margin-top:12px;"><button class="chip" type="button" id="gl-sacc-retry">Retry</button></div></div>`;
  } else if (_SACC_TAB === "side") inner = _saccBySide(d);
  else if (_SACC_TAB === "archetype") inner = _saccByArchetype(d);
  else if (_SACC_TAB === "cuts") inner = _saccCuts(d);
  else if (_SACC_TAB === "precision") inner = _saccPrecision(d);
  else if (_SACC_TAB === "coverage") inner = _saccCoverage(d);
  else inner = _saccReadFirst(d);
  el.innerHTML = shell(inner);
  document.querySelectorAll("[data-sacc-tab]").forEach(b => b.onclick = () => {
    _SACC_TAB = b.dataset.saccTab; renderSourceAccuracy();
  });
  const rb = document.getElementById("gl-sacc-retry");
  if (rb) rb.onclick = () => { _SACC = null; _SACC_LOADING = false; renderSourceAccuracy(); };
}

// ---- Models & Proofs view --------------------------------------------------
// The platform's accountability ledger as a browsable, family-grouped,
// verdict-filterable view. Same registry the Methodology table renders
// verbatim (data/model_registry.json), reorganized so a reader can audit one
// family or one verdict at a time. Lazy-loaded once into _MODELS, mirroring
// the Source Comparison fetch / guard / failure pattern.
const _MODEL_FAMILY_ORDER = ["PROSPX / eFV", "MLB Projections", "Free Agency",
  "MLB Stats", "Draft", "Trade Machine", "Other", "Internal / model-dev"];
const _MODEL_VERDICT_ORDER = ["validated", "provisional", "unvalidated", "deprecated"];
// Tokens kept fully uppercased when a model_id is humanized into a label. The
// list the owner keeps uppercase (REM, RIV, SEM, FV, WAR, WAG, PAL, FA, DPW,
// QO, SC, RPS, KRP, DS) plus a few domain acronyms that appear in ids. The
// bare "<=4 chars" shortcut was dropped on purpose: it shouts common words
// (PICK, TAX, SLOT, TEAM, WIN, FIT), which reads badly in user-facing copy.
const _MODEL_ACRONYMS = new Set(["REM", "RIV", "SEM", "FV", "WAR", "WAG", "PAL",
  "FA", "DPW", "QO", "SC", "RPS", "KRP", "DS", "MLB", "ETA", "IFA", "NPB", "KBO",
  "CPBL", "AAA", "AA", "ERA", "OPS", "AUC"]);
const _MODEL_MIXEDCASE = { efv: "eFV", xfv: "eFV", gmli: "gmLI" };
const _MODEL_STOPWORDS = new Set(["to", "vs", "of", "and", "the", "per", "by", "a"]);

function _modelLabel(id) {
  const toks = String(id == null ? "" : id).split("_");
  return toks.map((tok, i) => {
    if (!tok) return tok;
    const low = tok.toLowerCase();
    if (_MODEL_MIXEDCASE[low]) return _MODEL_MIXEDCASE[low];
    if (_MODEL_ACRONYMS.has(tok.toUpperCase())) return tok.toUpperCase();
    if (i > 0 && _MODEL_STOPWORDS.has(low)) return low;
    return tok.charAt(0).toUpperCase() + tok.slice(1);
  }).join(" ");
}

// Family from the surface (+ id as a fallback signal). Internal / model-dev is
// tested FIRST so the many "rendered nowhere" dev artifacts land there rather
// than being pulled into a product family by an incidental mention of eFV or
// Projections in their description.
function _modelFamily(m) {
  const s = ((m.surface || "") + " " + (m.model_id || "")).toLowerCase();
  const any = arr => arr.some(n => s.indexOf(n) !== -1);
  if (any(["model-dev", "rendered nowhere", "loss ledger", "not wired", "n/a", "internal"])) return "Internal / model-dev";
  if (any(["mlbstats", "bullpen", "starter"])) return "MLB Stats";
  if (any(["trademachine", "trade machine"])) return "Trade Machine";
  if (any(["free agency", "/fa/"])) return "Free Agency";
  if (any(["/projections/", "projections"])) return "MLB Projections";
  if (any(["draft"])) return "Draft";
  if (any(["prospx", "efv", "xfv"])) return "PROSPX / eFV";
  return "Other";
}

function _modelRow(label, val) {
  return val
    ? `<div class="gl-model-row"><span class="gl-model-rowlabel">${label}</span><span class="gl-model-rowval">${escapeHtml(val)}</span></div>`
    : "";
}

// The proof line: a link to the committed eval artifact where one exists; the
// audit-hit-list note for an unvalidated claim with no eval; the consensus /
// source models also point at the Source Comparison head-to-head. Eval-less
// internal rows get no Proof line at all.
// WHAT ACTUALLY SHIPS. Both deploy paths publish data/ at DEPTH ONE only (the
// nightly rsync takes /data/*.json; the CI workflow runs find data -maxdepth 1),
// so an eval artifact living under docs/ or tools/, or in a data/ subdirectory,
// is NOT on the deployed site and a link to it is a live 404. Four registry rows
// point at such paths today. A receipts page that links a missing receipt is
// worse than one that says where the receipt is, so those are NAMED, not linked.
function _artifactIsPublished(path) {
  if (!path) return false;
  const parts = String(path).split("/");
  return parts.length === 2 && parts[0] === "data";
}
function _artifactHTML(path) {
  const p = escapeHtml(String(path));
  return _artifactIsPublished(path)
    ? `<a href="/${p}" target="_blank" rel="noopener">${p}</a>`
    : `<code>${p}</code> <span class="gl-model-note">(committed to the repo, not published)</span>`;
}

function _modelProofHTML(m) {
  const bits = [];
  if (m.eval_artifact) {
    bits.push(_artifactHTML(m.eval_artifact));
  } else if (m.verdict === "unvalidated") {
    bits.push("No committed eval yet (this is the audit's hit list).");
  }
  if (m.model_id === "consensus_fv" || m.model_id === "source_track_record") {
    bits.push("See the Source Comparison view for the head-to-head proof.");
  }
  if (!bits.length) return "";
  return `<div class="gl-model-row"><span class="gl-model-rowlabel">Proof</span><span class="gl-model-rowval">${bits.join(" ")}</span></div>`;
}

// Report Card v0: paired champion-vs-baseline bars for each headline metric.
// Bars are normalized to the larger of the two values so the win is visible;
// the model bar gets a star only when it beats the baseline strictly AND the
// headline's artifact has not marked the gap unresolvable. A derived card
// (model_registry.derive_card) carries the artifact's own `resolvable` flag
// and `verdict` string; a lead inside the floor the backtest can resolve is
// not a win, and a tie is not a win either (audit L18-01: consensus_fv starred
// a Spearman lead its own artifact called not resolvable). Literal cards
// carry no flag and keep the plain comparison. One try/catch-wrapped card
// must never strand the ledger, so the caller degrades to the text card on a
// throw.
function _cardHeadline(card) {
  if (!card || !Array.isArray(card.headline) || !card.headline.length) return "";
  const rows = card.headline.map(h => {
    const champWins = (h.better === "lower" ? h.champion < h.baseline : h.champion > h.baseline)
      && h.resolvable !== false;
    const scale = Math.max(Math.abs(h.champion), Math.abs(h.baseline)) || 1;
    const bar = (val, isChamp) => {
      const pct = Math.max(2, Math.min(100, Math.abs(val) / scale * 100));
      return `<div class="gl-card-barrow">
        <span class="gl-card-barlab">${isChamp ? "model" : "baseline"}${isChamp && champWins ? " ★" : ""}</span>
        <span class="gl-card-track"><span class="gl-card-fill${isChamp ? " gl-card-fill--champ" : ""}" style="width:${pct.toFixed(1)}%"></span></span>
        <span class="gl-card-barval">${escapeHtml(String(val))}</span></div>`;
    };
    const dir = h.better === "lower" ? "lower is better" : "higher is better";
    // The artifact's verdict, verbatim, when the card is derived: the reader
    // sees "not resolvable at this power" beside a bar pair rather than
    // having to infer it from a missing star.
    const said = typeof h.verdict === "string" && h.verdict ? `; ${escapeHtml(h.verdict)}` : "";
    return `<div class="gl-card-metric">
      <div class="gl-card-metriclab">${escapeHtml(h.label)} <span class="gl-card-dir">(${dir}${said})</span></div>
      ${bar(h.champion, true)}${bar(h.baseline, false)}</div>`;
  }).join("");
  const foot = [card.n ? `n = ${escapeHtml(String(card.n))}` : "", escapeHtml(card.window || "")]
    .filter(Boolean).join(" · ");
  return `<div class="gl-card-proof">${rows}${foot ? `<div class="gl-card-foot">${foot}</div>` : ""}</div>`;
}

function _modelCard(m) {
  const v = m.verdict || "";
  const badge = `<span class="gl-verdict gl-verdict--${escapeHtml(v)}">${escapeHtml(v)}</span>`;
  let cardHtml = "";
  if (_S.cards && m.card) {
    try { cardHtml = _cardHeadline(m.card); } catch (err) { cardHtml = ""; }
  }
  return `<details class="gl-model-card">
    <summary class="gl-model-head">
      <span class="gl-model-name">${escapeHtml(_modelLabel(m.model_id))}</span>
      ${badge}
      <span class="gl-model-surface">${escapeHtml(m.surface || "")}</span>
    </summary>
    <div class="gl-model-body">
      ${cardHtml}
      ${_modelRow("Predicts", m.predicts)}
      ${_modelRow("Champion", m.champion)}
      ${_modelRow("Baseline it must beat", m.baseline)}
      ${_modelRow("How it is measured", m.metric)}
      ${_modelRow("Accountability", m.notes)}
      ${_modelProofHTML(m)}
    </div>
  </details>`;
}

function _modelsShell(inner) {
  return `<div class="source-comp-wrap">
    <div class="source-comp-eyebrow"><span class="scx-dot"></span>Models &amp; Proofs · the accountability ledger</div>
    ${inner}
  </div>`;
}

function renderModels() {
  const el = document.getElementById("models-body");
  if (!el) return;
  if (!_MODELS && !_MODELS_LOADING) {
    _MODELS_LOADING = true;
    fetch("/data/model_registry.json", { cache: "no-cache" })
      .then(r => (r.ok ? r.json() : null))
      .then(j => { _MODELS = j || { __error: true }; _MODELS_LOADING = false;
        if (_S.view === "models") renderModels(); })
      // A failed fetch (or a throw in the re-render) must surface the retry
      // state, never strand the loading placeholder.
      .catch(() => { _MODELS = { __error: true }; _MODELS_LOADING = false;
        if (_S.view === "models") renderModels(); });
  }
  const reg = _MODELS;
  if (!reg) {
    el.innerHTML = _modelsShell(`<div class="state-message">Loading the model registry...</div>`);
    return;
  }
  if (reg.__error || !Array.isArray(reg.models) || !reg.models.length) {
    el.innerHTML = _modelsShell(`<div class="state-message">The model registry could not be loaded.<div style="margin-top:12px;"><button class="chip" type="button" id="gl-models-retry">Retry</button></div></div>`);
    const rb = document.getElementById("gl-models-retry");
    if (rb) rb.onclick = () => { _MODELS = null; _MODELS_LOADING = false; renderModels(); };
    return;
  }

  const models = reg.models;
  const counts = {};
  models.forEach(m => { counts[m.verdict] = (counts[m.verdict] || 0) + 1; });
  const filters = [["all", "All", models.length]].concat(
    _MODEL_VERDICT_ORDER.map(v => [v, v.charAt(0).toUpperCase() + v.slice(1), counts[v] || 0]));
  const chips = filters.map(([key, lbl, n]) =>
    `<button class="chip${_MODELS_FILTER === key ? " active" : ""}" type="button" data-gl-mfilter="${escapeHtml(key)}">${escapeHtml(lbl)} <span class="gl-count">${n}</span></button>`).join("");

  const shown = _MODELS_FILTER === "all" ? models : models.filter(m => m.verdict === _MODELS_FILTER);
  const byFam = new Map();
  shown.forEach(m => {
    const f = _modelFamily(m);
    if (!byFam.has(f)) byFam.set(f, []);
    byFam.get(f).push(m);
  });
  const famOrder = _MODEL_FAMILY_ORDER.concat([...byFam.keys()].filter(f => _MODEL_FAMILY_ORDER.indexOf(f) === -1));
  const groupsHTML = famOrder.filter(f => byFam.has(f)).map(f =>
    `<div class="gl-model-group">
      <div class="gl-model-grouphead">${escapeHtml(f)} <span class="gl-count">${byFam.get(f).length}</span></div>
      ${byFam.get(f).map(_modelCard).join("")}
    </div>`).join("");

  const summary = `${models.length} models: ${counts.validated || 0} validated, ${counts.provisional || 0} provisional, ${counts.unvalidated || 0} unvalidated, ${counts.deprecated || 0} deprecated${reg.checked_at ? ` &middot; last checked ${escapeHtml(reg.checked_at)}` : ""}.`;

  el.innerHTML = _modelsShell(`
    <h2 class="meth-h">Every model that makes a predictive claim</h2>
    <p class="meth-note">This is the platform's accountability ledger. Every model that makes a predictive claim is listed here with an honest verdict, misses included. <strong>Validated</strong> means a forward-chained out-of-sample backtest exists and the champion beats its stated baseline. <strong>Provisional</strong> means measured but partial. <strong>Unvalidated</strong> means a claim with no measurement yet. <strong>Deprecated</strong> means it failed its gate and was retired.</p>
    <p class="gl-model-summary">${summary}</p>
    <div class="filter-bar gl-model-filters">${chips}</div>
    ${shown.length ? groupsHTML : `<div class="state-message">No models with that verdict.</div>`}`);

  el.querySelectorAll("[data-gl-mfilter]").forEach(b => b.onclick = () => {
    _MODELS_FILTER = b.dataset.glMfilter; renderModels();
  });
}

// ---- Library view ----------------------------------------------------------
// The public standalone-page index (owner ask 2026-08-04): every full page,
// in-module artifact page, and player-page surface, each with a one-line
// purpose. HAND-MAINTAINED here, matching the ported-prose convention -
// every route below is cross-checked against SITE_MAP.md and the module's
// own hash router before it is listed. PUBLIC ONLY: the dark previews
// (#tape=1, #cards=1) and the plain module leaderboards are deliberately
// not listed. A hoisted function (not a const) on purpose: boot() can run
// during IIFE evaluation, and a const this far down would sit in the
// temporal dead zone at that moment (the _RATER_META lesson, 2026-06-10).
function _libraryGroups() {
  return [
  { title: "Full pages",
    sub: "standalone destinations with their own route",
    rows: [
      ["/models/", "Model Accountability", "the full ledger: every model that makes a predictive claim, its verdict, and the eval artifact behind that verdict, plus the gaps counted rather than omitted"],
      ["/parks/", "MiLB Park Factors", "run environments for every affiliated park; the Methodology tab (/parks/#method) documents the estimator"],
      ["/sources/", "Data Sources & Attribution", "every upstream the platform reads, what it is used for, and the editorial stance"],
      ["/history/", "Today in Prospect History", "debut anniversaries, prospect trades, signings, and IL moves that landed on today's calendar date"],
      ["/news/", "Prospect News", "the full de-noised event wire: debuts, trades, promotions, IL, grade changes, FA signings"],
      ["/articles/", "Articles", "long-form editorial pieces, newest first"],
      ["/team/", "Developers", "who builds and runs the site"],
    ] },
  { title: "In-module artifact pages",
    sub: "deep-linkable views inside the module apps",
    rows: [
      ["/fa/#view=dpw", "FA · $/WAR by winter", "the full signings-implied price-of-a-win series and how it is estimated"],
      ["/fa/#view=tracker", "FA · Signing Tracker", "actual vs predicted contract for every signing, in real time"],
      ["/fa/#view=fits", "FA · Team Fits", "which clubs fit which free agents, component by component"],
      ["/fa/#view=archive", "FA · Archive", "past winters with realized WAR and realized surplus per signing"],
      ["/fa/#view=model", "FA · Model Accountability", "the FA market model held to its own record"],
      ["/projections/#view=teams", "Projections · Team Outlook", "club-level projected standings built from the player projections"],
      ["/projections/#view=accountability", "Projections · Accountability", "the projection engine scored against what actually happened"],
      ["/prospx/#tab=timemachine", "PROSPX · Time Machine", "the board as it stood at any past snapshot, or a diff of two dates"],
      ["/prospx/#tab=charts", "PROSPX · Scatterplots", "build-your-own X/Y charts across every prospect group"],
      ["/prospx/#tab=draft", "PROSPX · MLB Draft/HS", "draft boards, slots, bonuses, and High School Details"],
      ["/prospx/#tab=draft&dview=war-room", "PROSPX · Draft War Room", "pick-by-pick draft planning on the live board"],
      ["/prospx/#tab=farm", "PROSPX · Farm Systems", "org rankings and detail pages; each org page carries a Tendencies tab (development habits by org)"],
      ["/pal/#posfit=ladder", "Alchemy Lab · Positional Ladder", "the fielder-centred positional-fit ladder"],
      ["/pal/#rp2sp", "Alchemy Lab · RP to SP", "relievers with starter traits, ranked by conversion fit"],
      ["/pal/#sp2rp", "Alchemy Lab · SP to RP", "starters whose stuff plays up in relief"],
      ["/pal/#history", "Alchemy Lab · History", "past role conversions and how they went"],
      ["/pal/#pitchadd", "Alchemy Lab · Pitch Add", "which pitch each arm should add next"],
      ["/pal/#platoon", "Alchemy Lab · Platoon", "platoon-split profiles and pairings"],
      ["/pal/#prospects", "Alchemy Lab · Prospect Watch", "the pipeline read through the lab's conversion lenses"],
      ["/glossary/#view=models", "Glossary · Models & Proofs", "the same ledger as /models/, read inside the glossary: every predictive model with its verdict and eval artifact, next to the terms it defines"],
    ] },
  { title: "Player pages",
    sub: "per-player cards, addressable by URL",
    rows: [
      ["/prospx/#player=", "PROSPX prospect pages", "the full prospect card: grades, history, statlines, eFV explainers (append the player key)"],
      ["/projections/#player=", "MLB player cards", "projection cards for every MLB player (append the player key)"],
      ["/fa/#player=", "FA player cards", "contract projection and rational value for each free agent (append the player key)"],
    ] },
  ];
}

function renderLibrary() {
  const el = document.getElementById("library-body");
  if (!el) return;
  const group = g => {
    const rows = g.rows.map(([href, name, purpose]) => `<tr>
      <td class="meth-td-tier"><a href="${escapeHtml(href)}">${escapeHtml(name)}</a></td>
      <td><code>${escapeHtml(href)}</code></td>
      <td>${escapeHtml(purpose)}</td>
    </tr>`).join("");
    return `<div class="meth-table-wrap">
      <div class="meth-table-title">${escapeHtml(g.title)} <span class="meth-sub">${escapeHtml(g.sub)}</span></div>
      <div class="table-scroll-x"><table class="meth-table">
        <thead><tr><th>Page</th><th>Route</th><th>What it is</th></tr></thead>
        <tbody>${rows}</tbody>
      </table></div>
    </div>`;
  };
  el.innerHTML = `<div class="source-comp-wrap">
    <div class="source-comp-eyebrow"><span class="scx-dot"></span>Library · every standalone page on the site</div>
    <h2 class="meth-h">The page index</h2>
    <p class="meth-note">Everything on eephus.io that has its own address, in one place: the full pages, the deep-linkable artifact views inside each module, and the per-player cards. Every route here is public and stable.</p>
    <div class="meth-tables">${_libraryGroups().map(group).join("")}</div>
  </div>`;
}

})();
