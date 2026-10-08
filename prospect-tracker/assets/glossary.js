/* Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
 * Unauthorized copying of this file, via any medium is strictly prohibited
 * Proprietary and confidential
 * Written by Noah J. Dengler (@ARKNDJL), 2026 */

// =============================================================================
// eephus.io unified Glossary & Methodology app (/glossary/)
// =============================================================================
// Four shelves of views: Reference (Terms: seven term shelves, a provenance
// filter, A-Z, the index beside the selected entry, with artifact-derived
// receipt blocks on model entries via _receiptSpecs; How to Read: annotated
// anatomy guide; Formulas: every formula by shelf) · Methods
// (Methodology: seven chapters with a chapter rail, the industry-comparison
// chapter at #industry-comparison, the interactive teaching widgets and the
// PDF export) ·
// Evidence (Source Comparison: the empirical source-vs-source backtest;
// Source Accuracy: the who-grades-which-cohort measurement; Calibration: the
// live calibration monitor and what an eFV grade is worth; links to the
// /models/ ledger and /models/updates/) · Sources
// (Source Updates: the dates each outlet published a list; Page Index: every
// standalone page; a link to /sources/). The authoritative list is VIEWS
// below, mirrored by build_site.GLOSSARY_VIEWS.
// The guide/methodology/backtest
// renderers are PORTED from the retired PROSPX Glossary/Methodology tab
// (owner decision 2026-06-10); the data source for every definition is
// data/glossary.json via window.EEPHUS_GLOSSARY (assets/eephus-gl.js).
(function () {
  "use strict";

  const _S = { view: "terms", cat: "all", q: "", term: null,
               backtest: null, btLoading: false,
               // Terms view (LIBRARY_4): provenance and module filters, the
               // A-Z initial, the selected entry and the rows opened in place.
               prov: "all", mod: null, letter: null, sel: null, open: new Set(), secCounts: null };
  let GL = {};         // legacy-shaped map: slug -> {name, short, long, ...}
  // Source Accuracy view state. Declared HERE, at module scope above every
  // renderer: a `let` read from a hoisted
  // function that runs before the declaration is a temporal-dead-zone throw,
  // and a throw inside a fetch promise strands the view on "Loading" while
  // the smoke test stays green (the _RATER_META lesson, 2026-06-10).
  let _SACC = null;            // cached source_cohort_accuracy.json (or {__error:true})
  let _SACC_LOADING = false;   // in-flight guard against a double fetch
  let _SACC_TAB = "read-first"; // active sub-tab in the Source Accuracy view
  // Source Updates view state (owner ask 2026-10-02). Module scope for the
  // same TDZ reason as _SACC: the renderer is hoisted and boot can run first.
  let _SU = null;              // cached source updates payload (or {__error:true})
  let _SU_LOADING = false;     // in-flight guard against a double fetch
  // Receipt-block + industry-comparison artifact cache (2026-08-19). One map
  // keyed by fetch path, shared by the Terms-view receipt blocks and the
  // Methodology "Our tables vs the industry's" section, so an artifact two
  // consumers read is fetched exactly once. Declared here, module scope above
  // every renderer, for the same TDZ reason _SACC is.
  let _RCPT = {};          // fetch path -> parsed payload (or {__error:true})
  let _RCPT_LOADING = {};  // fetch path -> in-flight guard
  let _RCPT_SPECS = null;  // entry id -> receipt spec, built lazily by _receiptSpecs()
  // Glossary data state (SRE04, 2026-10-01): "loading" until eephus-gl.js
  // resolves data/glossary.json, then "ready"; "failed" on a rejected fetch.
  // Until "ready" every view paints the shared pixel state box
  // (assets/eephus-state.js) instead of an empty page under the search box.
  let _GL_STATE = "loading";

  // The module's display name (build_site.GLOSSARY_DISPLAY_NAME), read once
  // from the page root so visible copy never carries a literal module name.
  // Declared above boot() for the TDZ reason _SACC gives.
  const LIB_NAME = (() => {
    const a = document.querySelector(".gl-app");
    return (a && a.dataset && (a.dataset.displayName || a.dataset.moduleName)) || "page";
  })();

  // ---- the view registry (LIBRARY_3) ---------------------------------------
  // ONE ordered list of the shelves' leaves. The URL whitelist (with aliases),
  // the view -> container map and the render dispatch are generated from it;
  // build_site.GLOSSARY_VIEWS mirrors it to emit the strip and the containers,
  // and test_library_section_registry asserts the two lists are equal. An
  // outbound leaf (href) has no body and is a link in the strip; an unlisted
  // leaf opens from its URL but stays out of the strip until its task fills it.
  // One entry per line: the parity test reads this block line by line.
  const SHELVES = ["reference", "methods", "evidence", "sources"];
  const VIEWS = [
    { id: "terms", shelf: "reference", label: "Terms", body: "glossary-rows", render: renderTerms, aliases: [] },
    { id: "guide", shelf: "reference", label: "How to Read", body: "guide-body", render: renderGuide, aliases: [] },
    { id: "formulas", shelf: "reference", label: "Formulas", body: "formulas-body", render: renderFormulas, aliases: [] },
    { id: "methodology", shelf: "methods", label: "Methodology", body: "methodology-body", render: renderMethodology, aliases: [] },
    { id: "source-comparison", shelf: "evidence", label: "Source Comparison", body: "source-comparison-body", render: renderSourceComparison, aliases: [] },
    { id: "source-accuracy", shelf: "evidence", label: "Source Accuracy", body: "source-accuracy-body", render: renderSourceAccuracy, aliases: [] },
    { id: "calibration", shelf: "evidence", label: "Calibration", body: "calibration-body", render: renderCalibration, aliases: [] },
    { id: "models-ledger", shelf: "evidence", label: "Models", href: "/models/", aliases: [] },
    { id: "model-updates", shelf: "evidence", label: "Model Updates", href: "/models/updates/", aliases: [] },
    { id: "source-updates", shelf: "sources", label: "Source Updates", body: "source-updates-body", render: renderSourceUpdates, aliases: [] },
    { id: "data-sources", shelf: "sources", label: "Data Sources", href: "/sources/", aliases: [] },
    { id: "index", shelf: "sources", label: "Page Index", body: "index-body", render: renderLibrary, aliases: ["library"] },
  ];
  const VIEW_BY_ID = {};   // in-page view id -> registry entry
  const VIEW_OF = {};      // every accepted #view= value (ids and aliases) -> view id
  for (const v of VIEWS) {
    if (!v.body) continue;
    VIEW_BY_ID[v.id] = v;
    VIEW_OF[v.id] = v.id;
    for (const a of v.aliases) VIEW_OF[a] = v.id;
  }
  function _viewDef() { return VIEW_BY_ID[_S.view] || VIEW_BY_ID.terms; }
  // The alias table for leaves that left the Library for a page of their own
  // (LIBRARY_7, owner answer LB-Q2): an old #view= address forwards there,
  // carrying a family or verdict anchor when the hash held one.
  const FORWARDS = { models: "/models/" };

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
  // Returns true when the address forwards off the Library (the page is leaving).
  function syncFromURL() {
    const p = new URLSearchParams(location.hash.slice(1));
    const fwd = FORWARDS[p.get("view")];
    if (fwd) {
      const fam = (p.get("family") || "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
      const ver = (p.get("verdict") || "").toLowerCase();
      const anchor = fam ? "#family=" + fam
        : (/^(validated|provisional|unvalidated|deprecated)$/.test(ver) ? "#verdict=" + ver : "");
      location.replace(fwd + anchor);
      return true;
    }
    if (p.has("view")) {
      const v = VIEW_OF[p.get("view")];
      if (v) _S.view = v;
    }
    // #cat= takes a section or an old display group (_applyCat maps it);
    // #prov= and #mod= narrow by provenance and module.
    if (p.has("cat")) _applyCat(p.get("cat"));
    if (p.has("prov")) _S.prov = p.get("prov") || "all";
    if (p.has("mod")) _S.mod = p.get("mod") || null;
    if (p.has("q")) _S.q = p.get("q");
    // A Methods chapter: #view=methodology&ch=<chapter id>, or the bare
    // chapter id (#industry-comparison) the section has always carried.
    const bare = location.hash.slice(1);
    const ch = p.get("ch") || (_methChapters().some(c => c.id === bare) ? bare : null);
    if (ch) { _S.view = "methodology"; _S.methCh = ch; }
    _S.term = p.get("g") || null;
    if (_S.term) _S.view = "terms";
  }
  function syncToURL() {
    const p = new URLSearchParams();
    if (_S.view !== "terms") p.set("view", _S.view);
    if (_S.cat !== "all") p.set("cat", _S.cat);
    if (_S.prov !== "all") p.set("prov", _S.prov);
    if (_S.mod) p.set("mod", _S.mod);
    if (_S.q) p.set("q", _S.q);
    const g = _S.term || (_S.view === "terms" ? _S.sel : null);
    if (g) p.set("g", g);
    const h = p.toString();
    history.replaceState(null, "", h ? "#" + h : location.pathname);
  }

  // ---- Terms view (LIBRARY_4: seven term shelves, two panes) ----------------
  // Every entry carries `section`, one of SECTIONS (tools/glossary_sections.py
  // sets it from the entry's first module). The index groups by section, then
  // by the section's sub-groups; the provenance chip is a second filter row and
  // the A-Z strip filters the index to one initial. At 900 px and wider the
  // index sits left with the search above it and the selected entry reads on
  // the right; narrower, each row is one line that expands in place.
  const SECTIONS = ["Prospects", "Players & Stats", "Value & Contracts", "Clubs",
                    "Site & Methods", "Diamond", "Hall of Fame"];
  // The sprite symbol drawn beside each section heading.
  const SECTION_ICON = { "Prospects": "prospx", "Players & Stats": "mlbstats",
    "Value & Contracts": "fa", "Clubs": "ledger", "Site & Methods": "models",
    "Diamond": "diamond", "Hall of Fame": "hof" };
  // Sub-group headings in display order (Hall of Fame lists its four terms
  // under the section heading alone).
  const SUBGROUPS = {
    "Prospects": ["eFV and grades", "Scouting", "Badges", "Farm", "Levels"],
    "Players & Stats": ["Hitting", "Pitching", "Statcast", "WAR family", "Alchemy Lab", "Scores / Standings"],
    "Value & Contracts": ["Surplus and $/WAR", "Free agency", "Arbitration", "Rules and transactions", "Trade Machine"],
    "Clubs": ["Franchise", "Club Ledger", "In-Game Management"],
    "Site & Methods": ["Platform features", "Model verdicts"],
    "Diamond": ["Betting", "Fantasy"],
    "Hall of Fame": [""],
  };
  // Old #cat= values (the retired display groups) -> [section, module, provenance].
  const LEGACY_CAT = {
    "Free Agency": ["Value & Contracts", "fa", null],
    "Platform & Methodology": ["Site & Methods", null, null],
    "Arkmetrics": ["all", null, "ark"],
    "Statistical Foundations": ["Players & Stats", null, null],
    "Statcast & Tracking": ["Players & Stats", null, null],
    "MLB Rules & Transactions": ["Value & Contracts", null, null],
    "Prospect Grades & Scouting": ["Prospects", null, null],
    "Badges & Indicators": ["Prospects", null, null],
    "Levels & Leagues": ["Prospects", null, null],
    "Betting & Markets": ["Diamond", "betting", null],
    "Fantasy & DFS": ["Diamond", "fantasy", null],
    "industry": ["Hall of Fame", null, null],
    "method": ["Hall of Fame", null, null],
  };
  const PROVENANCE = [["ark", "ARKMETRIC", "eephus.io original"],
                      ["industry", "INDUSTRY", "external metric, credited"],
                      ["foundation", "FOUNDATION", "shared concept or standard stat"]];
  const MOD_LABEL = { prospx: "PROSPX", fa: "MLB FA", foundations: "FOUNDATIONS",
                      platform: "PLATFORM", franchise: "FRANCHISES", scores: "SCORES / STANDINGS" };

  function entrySection(e) { return SECTIONS.includes(e.section) ? e.section : "Site & Methods"; }

  const _FARM_IDS = new Set(["sur_plus", "fv_per_m_pool", "ifa_dollars_per_fv", "draft_ceiling_hits",
                             "draft_overperformance", "waiver_hit_rate", "trade_war_delta"]);
  const _PITCH_RE = /^(x?sem_plus|x?rem_plus|riv_plus|bullpen_plus|rotation_plus|gmli|skill_fip|reliever_roles|k_bb_pct)/;
  const _DPW_IDS = new Set(["winter_dpw", "contract_surplus", "rational_value", "deferral_npv"]);
  function subGroup(slug, e, sec) {
    const cat = e.category, m0 = (e.module || [])[0];
    if (sec === "Prospects") {
      if (cat === "level") return "Levels";
      if (cat === "indicators" || cat === "status") return "Badges";
      if (cat === "farm" || /^(farm_|fin_|mlb_production_)/.test(slug) || _FARM_IDS.has(slug)) return "Farm";
      if (["scouting", "definition", "statcast", "hitter-stat"].includes(cat)) return "Scouting";
      return "eFV and grades";
    }
    if (sec === "Players & Stats") {
      if (m0 === "pal") return "Alchemy Lab";
      if (m0 === "scores") return "Scores / Standings";
      if (cat === "statcast") return "Statcast";
      if (cat === "general-stat" || cat === "industry-stat" || /^war|dem_plus/.test(slug)) return "WAR family";
      if (cat === "pitcher-stat" || _PITCH_RE.test(slug)) return "Pitching";
      return "Hitting";
    }
    if (sec === "Value & Contracts") {
      if (m0 === "arbitration" || cat === "Valuation" || slug === "arbitration") return "Arbitration";
      if (m0 === "trademachine") return "Trade Machine";
      if (cat === "financial" || _DPW_IDS.has(slug)) return "Surplus and $/WAR";
      if (m0 === "fa") return "Free agency";
      return "Rules and transactions";
    }
    if (sec === "Clubs") {
      if (m0 === "franchise") return "Franchise";
      if (m0 === "management") return "In-Game Management";
      return "Club Ledger";
    }
    if (sec === "Site & Methods") {
      return (cat === "methodology" || cat === "general-stat") ? "Model verdicts" : "Platform features";
    }
    if (sec === "Diamond") return m0 === "fantasy" ? "Fantasy" : "Betting";
    return "";
  }

  // The pixel sprite's versioned url, read from an icon the page already draws.
  function _spriteURL() {
    const u = document.querySelector('use[href*="/assets/eephus-icons.svg"]');
    return u ? String(u.getAttribute("href")).split("#")[0] : "/assets/eephus-icons.svg";
  }
  function _secIcon(sec) {
    const k = SECTION_ICON[sec];
    return k ? `<svg class="ico gl-sec-ico" width="16" height="16" viewBox="0 0 16 16" aria-hidden="true" focusable="false"><use href="${_spriteURL()}#i-${k}"/></svg>` : "";
  }

  // Two panes at 900 px and wider (site.css carries the same breakpoint).
  function _wide() { return !!(window.matchMedia && window.matchMedia("(min-width: 900px)").matches); }

  // Translate an old #cat= value into the section, module and provenance filters.
  function _applyCat(v) {
    _S.mod = null; _S.prov = "all";
    if (!v || v === "all" || SECTIONS.includes(v)) { _S.cat = v || "all"; return; }
    const m = LEGACY_CAT[v];
    if (m) { _S.cat = m[0]; _S.mod = m[1]; _S.prov = m[2] || "all"; return; }
    _S.cat = "all";
  }

  function moduleBadges(e) {
    return (e.module || []).map(m =>
      `<span class="gl-mod gl-mod--${m}">${MOD_LABEL[m] || m.toUpperCase()}</span>`).join("");
  }

  // Provenance chip: distinguishes our own models from borrowed industry
  // metrics and shared foundations, so a reader always knows what is ours.
  function shelfBadge(e) {
    const s = PROVENANCE.find(p => p[0] === e.shelf);
    return s ? `<span class="gl-shelf gl-shelf--${e.shelf}" title="${s[2]}">${s[1]}</span>` : "";
  }

  // The full read of one entry: method, formula, example, origin, visual,
  // receipt slot and See also. Shared by the right pane and an opened row.
  function _entryParts(slug, e) {
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
    // an artifact-derived receipt. The slot is filled when the entry is read
    // (_wireReceipts), so a page of closed rows costs zero fetches.
    if (_receiptSpecs()[slug]) {
      more.push(`<div class="gl-receipt-slot" data-receipt="${escapeHtml(slug)}"></div>`);
    }
    const rel = (e.related || []).filter(r => GL[r]).map(r =>
      `<a class="gl-rel" href="#g=${escapeHtml(r)}">${escapeHtml(GL[r].name)}</a>`).join("");
    if (rel) more.push(`<div class="gl-relrow"><span class="gl-microlabel">See also</span>${rel}</div>`);
    return more.join("");
  }

  function _fullName(e) {
    const alt = (e.aliases || []).filter(a => a !== e.name && a.includes(" "));
    return alt.length ? alt.sort((a, b) => b.length - a.length)[0] : "";
  }

  // The right pane's read of the selected entry.
  function _entryPane(slug, e) {
    const sec = entrySection(e), sub = subGroup(slug, e, sec), fn = _fullName(e);
    return `<article class="gl-entry-card" data-slug="${escapeHtml(slug)}">
      <div class="gl-entry-where">${_secIcon(sec)}${escapeHtml(sec)}${sub ? " · " + escapeHtml(sub) : ""}</div>
      <div class="gl-card-head">
        <h2 class="gp-term">${escapeHtml(e.name)}</h2>
        ${fn ? `<span class="gl-fullname">(${escapeHtml(fn)})</span>` : ""}
        <span class="gl-badges">${shelfBadge(e)}${moduleBadges(e)}</span>
      </div>
      <div class="gl-def">${escapeHtml(e.short)}</div>
      <div class="gl-entry-body">${_entryParts(slug, e)}</div>
    </article>`;
  }

  // The right pane before a term is chosen: the shelves with their counts.
  function _entryOverview(counts, total) {
    const rows = SECTIONS.map(s => `<li><button class="gl-ov-sec" type="button" data-gl-ov="${escapeHtml(s)}">${_secIcon(s)}<span>${escapeHtml(s)}</span><span class="gl-count">${counts[s] || 0}</span></button>
      <span class="gl-ov-subs">${SUBGROUPS[s].filter(Boolean).map(escapeHtml).join(", ")}</span></li>`).join("");
    return `<div class="gl-entry-overview">
      <p class="gl-entry-lede">${total} terms on ${SECTIONS.length} shelves. Pick a term in the index to read its definition, method, formula and example here.</p>
      <ul class="gl-ov-list">${rows}</ul></div>`;
  }

  // One index row: the provenance dot, the name and the short definition
  // (clipped to two lines on a phone, hidden beside the right pane).
  function _row(slug, e) {
    const open = _S.open.has(slug), sel = _S.sel === slug;
    const prov = PROVENANCE.find(p => p[0] === e.shelf);
    return `<div class="glossary-card gl-row${open ? " is-open" : ""}${sel ? " is-selected" : ""}" id="g-${escapeHtml(slug)}" data-slug="${escapeHtml(slug)}">
      <button class="gl-row-head" type="button" aria-expanded="${open ? "true" : "false"}"${sel ? ' aria-current="true"' : ""}>
        <span class="gl-dot gl-dot--${escapeHtml(e.shelf || "none")}" title="${prov ? prov[1] : ""}" aria-hidden="true"></span>
        <span class="gl-row-name">${escapeHtml(e.name)}</span>
        <span class="gl-row-def">${escapeHtml(e.short)}</span>
      </button>
      <div class="gl-row-body"${open ? "" : " hidden"}>${open ? `<div class="gl-badges gl-row-badges">${shelfBadge(e)}${moduleBadges(e)}</div>${_entryParts(slug, e)}` : ""}</div>
    </div>`;
  }

  function _initial(e) {
    const c = (e.name[0] || "#").toUpperCase();
    return /[A-Z]/.test(c) ? c : "#";
  }

  // The panes are drawn once; later renders repaint the index and the entry
  // only, so the search box (moved into the index head) keeps its focus.
  function _termsShell(root) {
    if (root.querySelector(".gl-terms")) return;
    root.innerHTML = `<div class="gl-terms">
      <div class="gl-index-pane"><div class="gl-index-head"><div class="gl-index-note" id="gl-index-note" aria-live="polite"></div></div>
        <nav class="gl-index" id="gl-index" aria-label="Term index"></nav></div>
      <section class="gl-entry-pane" id="gl-entry" aria-label="Selected term"></section></div>`;
    const inp = document.getElementById("gl-search");
    if (inp) root.querySelector(".gl-index-head").prepend(inp);
    root.querySelector("#gl-index").addEventListener("click", ev => {
      const head = ev.target.closest(".gl-row-head");
      if (!head) return;
      const slug = head.closest(".gl-row").dataset.slug;
      if (_wide()) _selectTerm(slug, false);
      else _toggleRow(slug);
    });
    root.querySelector("#gl-index-note").addEventListener("click", ev => {
      if (!ev.target.closest("[data-gl-mod-clear]")) return;
      _S.mod = null; syncToURL(); render();
    });
    root.querySelector("#gl-entry").addEventListener("click", ev => {
      const b = ev.target.closest("[data-gl-ov]");
      if (!b) return;
      _S.cat = b.dataset.glOv; syncToURL(); render();
    });
  }

  function _paintEntry() {
    const pane = document.getElementById("gl-entry");
    if (!pane) return;
    // Below the breakpoint the pane is not shown and rows open in place.
    if (!_wide()) { pane.innerHTML = ""; return; }
    const e = _S.sel && GL[_S.sel];
    if (e) {
      pane.innerHTML = _entryPane(_S.sel, e);
      _wireReceipts(pane);
    } else {
      pane.innerHTML = _entryOverview(_S.secCounts || {}, Object.keys(GL).length);
    }
  }

  function _selectTerm(slug, fromURL) {
    _S.sel = slug;
    syncToURL();
    document.querySelectorAll("#gl-index .gl-row").forEach(r => {
      const on = r.dataset.slug === slug;
      r.classList.toggle("is-selected", on);
      const h = r.querySelector(".gl-row-head");
      if (on) h.setAttribute("aria-current", "true"); else h.removeAttribute("aria-current");
    });
    _paintEntry();
    const pane = document.getElementById("gl-entry");
    if (!fromURL && pane && pane.getBoundingClientRect().top < 0) pane.scrollIntoView({ block: "start" });
  }

  function _toggleRow(slug) {
    if (_S.open.has(slug)) _S.open.delete(slug); else _S.open.add(slug);
    const row = document.getElementById("g-" + slug);
    if (!row || !GL[slug]) return;
    row.outerHTML = _row(slug, GL[slug]);
    const fresh = document.getElementById("g-" + slug);
    if (fresh && _S.open.has(slug)) _wireReceipts(fresh);
  }

  function renderTerms() {
    const root = document.getElementById("glossary-rows");
    _termsShell(root);
    const q = (_S.q || "").toLowerCase().trim();
    // An entry reached by #g= must be on the index: filters that hide it clear.
    // A retired slug resolves through eephus-gl.js (enter_prob opens p_enter).
    if (_S.term && !GL[_S.term]) {
      const G = window.EEPHUS_GL;
      const c = G && G.canon ? G.canon(_S.term) : null;
      _S.term = c && GL[c] ? c : null;
    }
    if (_S.term) {
      const t = GL[_S.term];
      if ((_S.cat !== "all" && entrySection(t) !== _S.cat) || (_S.prov !== "all" && t.shelf !== _S.prov)
          || (_S.mod && !(t.module || []).includes(_S.mod)) || (_S.letter && _initial(t) !== _S.letter)) {
        _S.cat = "all"; _S.prov = "all"; _S.mod = null; _S.letter = null;
      }
    }
    const items = [];
    for (const [slug, e] of Object.entries(GL)) {
      if (q && !(_S.term === slug)) {
        const hay = (e.name + " " + (e.aliases || []).join(" ") + " " +
                     e.short + " " + (e.long || "")).toLowerCase();
        if (!hay.includes(q)) continue;
      }
      if (_S.mod && !(e.module || []).includes(_S.mod)) continue;
      items.push({ slug, e, sec: entrySection(e), prov: e.shelf, ini: _initial(e) });
    }
    // Facet counts: each row of chips counts what the other filters leave.
    const secCounts = { all: 0 }, provCounts = { all: 0 }, letters = new Set();
    for (const it of items) {
      const okSec = _S.cat === "all" || it.sec === _S.cat;
      const okProv = _S.prov === "all" || it.prov === _S.prov;
      const okL = !_S.letter || it.ini === _S.letter;
      if (okProv && okL) { secCounts.all++; secCounts[it.sec] = (secCounts[it.sec] || 0) + 1; }
      if (okSec && okL) { provCounts.all++; provCounts[it.prov] = (provCounts[it.prov] || 0) + 1; }
      if (okSec && okProv) letters.add(it.ini);
    }
    _S.secCounts = secCounts;
    const pressed = on => ` aria-pressed="${on ? "true" : "false"}"`;
    document.getElementById("gl-cats").innerHTML =
      [`<button class="chip${_S.cat === "all" ? " active" : ""}" type="button"${pressed(_S.cat === "all")} data-gl-cat="all">All <span class="gl-count">${secCounts.all}</span></button>`]
      .concat(SECTIONS.map(s =>
        `<button class="chip gl-sec-chip${_S.cat === s ? " active" : ""}" type="button"${pressed(_S.cat === s)} data-gl-cat="${escapeHtml(s)}">${_secIcon(s)}${escapeHtml(s)} <span class="gl-count">${secCounts[s] || 0}</span></button>`))
      .join("");
    document.querySelectorAll("[data-gl-cat]").forEach(b => b.onclick = () => {
      _S.cat = b.dataset.glCat; syncToURL(); render();
    });
    // On a phone the chip bar swipes sideways: keep the active section in view.
    const cats = document.getElementById("gl-cats"), act = cats.querySelector(".chip.active");
    if (act && cats.scrollWidth > cats.clientWidth) cats.scrollLeft = Math.max(0, act.offsetLeft - cats.offsetLeft - 8);
    const prov = document.getElementById("gl-prov");
    if (prov) {
      prov.innerHTML = `<span class="gl-microlabel gl-prov-label">Provenance</span>` +
        [["all", "ANY", "every provenance"]].concat(PROVENANCE).map(([k, lbl, ttl]) =>
          `<button class="chip gl-prov-chip${_S.prov === k ? " active" : ""}" type="button"${pressed(_S.prov === k)} data-gl-prov="${k}" title="${ttl}">${k === "all" ? "" : `<span class="gl-dot gl-dot--${k}" aria-hidden="true"></span>`}${lbl} <span class="gl-count">${provCounts[k] || 0}</span></button>`).join("");
      prov.querySelectorAll("[data-gl-prov]").forEach(b => b.onclick = () => {
        _S.prov = b.dataset.glProv; syncToURL(); render();
      });
    }
    // A-Z strip: one initial at a time narrows the index (inactive letters
    // dimmed, never hidden); the active letter again clears it.
    const az = ["#"].concat("ABCDEFGHIJKLMNOPQRSTUVWXYZ".split("")).map(L => {
      const on = _S.letter === L;
      return letters.has(L) || on
        ? `<a href="#" data-gl-az="${L}"${on ? ' class="active" aria-current="true"' : ""}>${L}</a>`
        : `<span class="gl-az-off">${L}</span>`;
    }).join("");
    document.getElementById("gl-az").innerHTML = az;
    document.querySelectorAll("[data-gl-az]").forEach(a => a.onclick = ev => {
      ev.preventDefault();
      const L = a.dataset.glAz;
      _S.letter = _S.letter === L ? null : L;
      render();
    });
    // The index: section heading (icon, count), sub-group heading, rows A to Z.
    const shown = items.filter(it => (_S.cat === "all" || it.sec === _S.cat)
      && (_S.prov === "all" || it.prov === _S.prov) && (!_S.letter || it.ini === _S.letter));
    const bySec = new Map();
    for (const it of shown) {
      if (!bySec.has(it.sec)) bySec.set(it.sec, new Map());
      const sub = subGroup(it.slug, it.e, it.sec);
      const m = bySec.get(it.sec);
      if (!m.has(sub)) m.set(sub, []);
      m.get(sub).push(it);
    }
    const parts = [];
    for (const sec of SECTIONS) {
      const m = bySec.get(sec);
      if (!m) continue;
      const n = [...m.values()].reduce((a, l) => a + l.length, 0);
      parts.push(`<div class="glossary-cat-heading gl-sec-head" data-gl-sec="${escapeHtml(sec)}">${_secIcon(sec)}<span>${escapeHtml(sec)}</span><span class="gl-count">${n}</span></div>`);
      const order = SUBGROUPS[sec].concat([...m.keys()].filter(k => !SUBGROUPS[sec].includes(k)));
      for (const sub of order) {
        const list = m.get(sub);
        if (!list) continue;
        if (sub) parts.push(`<div class="gl-sub-head">${escapeHtml(sub)} <span class="gl-count">${list.length}</span></div>`);
        list.sort((a, b) => a.e.name.localeCompare(b.e.name, "en", { sensitivity: "base" }));
        for (const it of list) parts.push(_row(it.slug, it.e));
      }
    }
    const idx = document.getElementById("gl-index");
    idx.innerHTML = parts.join("") || `<div class="state-message">No terms match.</div>`;
    _wireReceipts(idx);
    const note = document.getElementById("gl-index-note");
    if (note) {
      note.innerHTML = `${shown.length} of ${Object.keys(GL).length} terms` +
        (_S.mod ? ` · ${escapeHtml(MOD_LABEL[_S.mod] || _S.mod.toUpperCase())} terms only <button class="gl-linkbtn" type="button" data-gl-mod-clear>Show every module</button>` : "");
    }
    if (_S.sel && !GL[_S.sel]) _S.sel = null;
    // A #g= arrival: select the entry (wide) or open its row (narrow), scroll
    // the index to it and flash it once.
    if (_S.term) {
      const slug = _S.term;
      _S.term = null;
      _S.sel = slug;
      if (!_wide()) {
        _S.open.add(slug);
        const row = document.getElementById("g-" + slug);
        if (row) { row.outerHTML = _row(slug, GL[slug]); _wireReceipts(document.getElementById("g-" + slug)); }
      }
      _paintEntry();
      const row = document.getElementById("g-" + slug);
      if (row) {
        row.classList.add("is-selected");
        const h = row.querySelector(".gl-row-head");
        if (h) h.setAttribute("aria-current", "true");
        requestAnimationFrame(() => {
          if (_wide()) {
            idx.scrollTop = Math.max(0, row.offsetTop - idx.offsetTop - idx.clientHeight / 3);
            const pane = document.querySelector(".gl-terms");
            if (pane) pane.scrollIntoView({ block: "start" });
          } else {
            row.scrollIntoView({ behavior: "smooth", block: "start" });
          }
          row.classList.add("is-highlighted");
        });
      }
    } else {
      _paintEntry();
    }
  }

  // ---- Formulas view (LIBRARY_4) ---------------------------------------------
  // Every entry whose formula is a non-blank string, by section, in the
  // site's monospace; each name opens its entry under Terms. No new data.
  function renderFormulas() {
    const el = document.getElementById("formulas-body");
    if (!el) return;
    const bySec = new Map(SECTIONS.map(s => [s, []]));
    let n = 0;
    for (const [slug, e] of Object.entries(GL)) {
      if (typeof e.formula !== "string" || !e.formula.trim()) continue;
      bySec.get(entrySection(e)).push([slug, e]);
      n++;
    }
    const nav = SECTIONS.filter(s => bySec.get(s).length).map(s =>
      `<button class="chip gl-sec-chip" type="button" data-gl-fx-jump="${escapeHtml(s)}">${_secIcon(s)}${escapeHtml(s)} <span class="gl-count">${bySec.get(s).length}</span></button>`).join("");
    const secs = SECTIONS.filter(s => bySec.get(s).length).map(s => {
      const list = bySec.get(s).sort((a, b) => a[1].name.localeCompare(b[1].name, "en", { sensitivity: "base" }));
      return `<section class="gl-fx-sec" data-gl-fx-sec="${escapeHtml(s)}">
        <h3 class="glossary-cat-heading gl-sec-head">${_secIcon(s)}<span>${escapeHtml(s)}</span><span class="gl-count">${list.length}</span></h3>
        <dl class="gl-fx-list">${list.map(([slug, e]) =>
          `<div class="gl-fx-row" data-fx-slug="${escapeHtml(slug)}"><dt><a class="gl-fx-term" href="#g=${escapeHtml(slug)}">${escapeHtml(e.name)}</a></dt><dd><pre class="gl-fx-pre">${escapeHtml(e.formula)}</pre></dd></div>`).join("")}</dl>
      </section>`;
    }).join("");
    el.innerHTML = `<div class="gl-fx">
      <p class="gl-fx-lede">${n} entries carry a formula, grouped by shelf. Each name opens its full entry under Terms.</p>
      <div class="filter-bar gl-fx-nav">${nav}</div>${secs}</div>`;
    el.querySelectorAll("[data-gl-fx-jump]").forEach(b => b.onclick = () => {
      const t = el.querySelector(`[data-gl-fx-sec="${b.dataset.glFxJump}"]`);
      if (t) t.scrollIntoView({ block: "start" });
    });
  }

  // ==== RECEIPT BLOCKS (2026-08-19) ==========================================
  // Artifact-derived receipts on model entries: the estimand in one plain
  // sentence, the named baseline, the measured number with its floor or CI,
  // and a three-valued verdict chip (clears floor / inside floor / trails).
  // Every figure is read from the committed eval artifact at expand time and
  // passes through ONE formatter (_rn); no measured number is typed by hand.
  // Ledger notes, recorded rather than approximated:
  //   - milb_park_factor: no receipt spec. Its entry types no measured
  //     figure; the stability reads are computed live on /parks/#method
  //     from the served park table.
  //   - war_pa_plus_3yr / _adj and the war_ip_plus_* 3yr/adj variants: the
  //     committed eval (war_rate_plus_eval.json) scores only the base
  //     single-season indexes, so the variants get NO receipt (no clean key).
  //   - the IFA $1M step prior has no glossary entry of its own; its receipt
  //     rides the `ifa` entry. The pWOBA gate (phem_marcel_lite_eval.json,
  //     where fa_projection's projected wOBA won) rides the `pwoba` entry.
  //   - hem_plus_3yr / sem_plus_3yr / rem_plus_3yr / xrem_plus / xsem_plus: no
  //     per-variant eval cell; skipped, not approximated. fwdhem_plus reads the
  //     served column's cell (rung D4) of its 2026-09-18 re-gate.

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
      // The served column (ladder rung D4, integers as served), not the
      // eval-normalized construction the 2026-07 gate scored: the re-gate
      // demoted the row to provisional on exactly these two cells.
      fwdhem_plus: {
        art: "/data/xhem_served_regate_eval.json",
        estimand: "Does the xHEM+ Blend, as the board serves it, predict next-season wOBA better than xwOBA alone?",
        baseline: "Savant xwOBA alone, same forward pairs",
        read: j => {
          const d4 = ((((j.arms || {}).A2_fwdhem_plus || {}).ladder) || {}).D4 || {};
          const n = (j.n_forward_pairs || {}).A2;
          const cell = (v, label) => {
            const g = (v && v.gap_ci) || {};
            if (!v || v.rho_primary == null || v.rho_baseline == null || g.lo95 == null) return null;
            return {
              label: label + (n != null ? " (n=" + _rn(n, 0) + " forward pairs)" : ""),
              mv: _rn(v.rho_primary), mname: "xHEM+ Blend", bname: "xwOBA", bv: _rn(v.rho_baseline),
              band: "gap " + _rns(g.mean) + ", 95% CI " + _rns(g.lo95) + " to " + _rns(g.hi95),
              verdict: _rcptCI(g.lo95, g.hi95),
            };
          };
          const rows = [cell(d4.v1, "Spearman rho, next-season wOBA"),
                        cell(d4.v2, "Same read, clustered bootstrap")].filter(Boolean);
          return rows.length ? rows : null;
        },
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
        baseline: "unflagged board players drawn at random from the flag's own FV band x level x age band on the emit night, scored over the same window on the same board history",
        read: j => {
          const v2 = j.v2 || {}, t = v2.by_flag_type || {}, ba = j.before_after || {};
          const _z = v => (v != null && Math.abs(Number(v)) < 0.0005 ? 0 : v);   // no negative zero
          const rows = [];
          [["riser", "Riser flags: board FV up 5 or more"],
           ["rebound", "Rebound flags: board FV up 5 or more"],
           ["faller", "Faller flags: board FV down 5 or more"]].forEach(pair => {
            ["h30", "h60"].forEach(hk => {
              const f = ((t[pair[0]] || {}).horizons || {})[hk];
              if (!f || f.hit_rate == null || f.control_rate == null || !Array.isArray(f.gap_ci)) return;
              const was = (((ba[pair[0]] || {})[hk]) || {}).before || {};
              rows.push({
                label: pair[1] + " within " + hk.slice(1) + " days (n=" + _rn(f.n, 0) + " flags, " + _rn(f.players, 0) + " players)",
                mv: _rnp(f.hit_rate), bname: "matched control (n=" + _rn(f.control_n, 0) + ")", bv: _rnp(f.control_rate),
                band: "gap " + _rns(Number(f.gap) * 100, 1) + " pts, 95% CI " + _rnp(_z(f.gap_ci[0])) + " to " + _rnp(_z(f.gap_ci[1])) + " (clustered by player)"
                  + (was.hit_rate != null ? "; before the re-score " + _rnp(was.hit_rate) + " vs " + _rnp(was.control_rate) : ""),
                verdict: ["clears", "inside", "trails"].indexOf(f.verdict) >= 0 ? f.verdict : "inside",
                title: "v2 verdict as recorded in the artifact",
              });
            });
          });
          return rows.length ? rows : null;
        },
        note: j => {
          const t = ((j.v2 || {}).by_flag_type) || {};
          const k = Object.keys(t).filter(x => ((t[x] || {}).kill_rule || {}).verdict_recommendation === "deprecated");
          return "Re-scored " + ((j.v2 || {}).registered || "") + " (v2): flags and controls both read the board's own consensus FV from the night of each run, controls are a seeded random draw from the flag's cell, cohorts are calendar months and intervals are clustered by player. The earlier version scored flags and controls on different FV bases against the first unflagged players by key; its rates are kept in the artifact as the before column."
            + (k.length ? " The registered kill rule now recommends deprecating: " + k.join(", ") + ". Whether any bucket changes is the owner's call." : "");
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
            label: "Spearman rho vs realized WAR, " + _hhFrameName(hh) + " (n=" + _rn(hh.n, 0) + ")",
            mv: _rn(hh.xfv_spearman, 4), bname: "consensus", bv: _rn(hh.consensus_spearman, 4),
            band: "gap " + _rns(hh.delta, 4) + " vs a floor of " + _rn(hh.mde95, 4) + (hh.mde95_status === "carried" ? " (carried from vm1)" : ""),
            verdict: hh.resolvable === true ? (hh.xfv_beats === true ? "clears" : "trails") : "inside",
            title: "head_to_head_verdict as recorded in the artifact",
          }];
        },
        // Derived from the same verdict, never typed (the reading used to be fixed prose).
        note: j => {
          const hh = ((j && j.accuracy) || {}).head_to_head_verdict;
          if (!hh || hh.resolvable == null) return "";
          return hh.resolvable === true
            ? "The gap clears the floor this backtest can resolve. The full derived verdict renders in Source Comparison."
            : "The honest reading is a tie: the gap sits inside the floor this backtest can resolve, so eFV and the consensus are statistically indistinguishable on ordering. The full derived verdict renders in Source Comparison.";
        },
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
    const def = _viewDef();
    // The strip: aria-current="page" on the active leaf and "true" on its
    // shelf, one state attribute per chip; only the active shelf's leaf row
    // shows, and an unlisted leaf shows its chip only while it is current.
    document.querySelectorAll("[data-glossary-view]").forEach(b => {
      const on = b.dataset.glossaryView === def.id;
      b.classList.toggle("active", on);
      if (on) b.setAttribute("aria-current", "page"); else b.removeAttribute("aria-current");
      if (b.hasAttribute("data-gl-unlisted")) b.hidden = !on;
    });
    document.querySelectorAll("[data-gl-shelf-chip]").forEach(b => {
      const on = b.dataset.glShelfChip === def.shelf;
      b.classList.toggle("active", on);
      if (on) b.setAttribute("aria-current", "true"); else b.removeAttribute("aria-current");
    });
    document.querySelectorAll("[data-gl-leaves]").forEach(r => { r.hidden = r.dataset.glLeaves !== def.shelf; });
    for (const v of Object.values(VIEW_BY_ID)) {
      const el = document.getElementById(v.body);
      if (el) el.style.display = v.id === def.id ? "" : "none";
    }
    const bar = document.getElementById("gl-termbar");
    if (bar) bar.style.display = _S.view === "terms" ? "" : "none";
    // The group chips and A-Z strip stay hidden until the terms exist, so a
    // loading or failed page shows no empty bordered bar above the state box.
    for (const id of ["gl-cats", "gl-prov", "gl-az"]) {
      const el = document.getElementById(id);
      if (el) el.style.display = _GL_STATE === "ready" ? "" : "none";
    }
    if (_GL_STATE !== "ready") { _paintGlState(document.getElementById(def.body)); return; }
    def.render();
  }

  // On load the active leaf chip is brought into view (the strip wraps, so
  // this only moves the page when the strip itself sits off screen).
  function _scrollActiveChip() {
    const a = document.querySelector('[data-glossary-view][aria-current="page"]');
    if (a && a.scrollIntoView) a.scrollIntoView({ block: "nearest", inline: "nearest" });
  }

  function boot() {
    if (syncFromURL()) return;
    document.querySelectorAll("[data-glossary-view]").forEach(b => {
      b.onclick = () => { _S.view = b.dataset.glossaryView; syncToURL(); render(); };
    });
    // A shelf chip opens the shelf's first listed in-page leaf.
    document.querySelectorAll("[data-gl-shelf-chip]").forEach(b => {
      b.onclick = () => {
        const sh = b.dataset.glShelfChip;
        if (_viewDef().shelf === sh) return;
        const first = VIEWS.find(v => v.shelf === sh && v.body && !v.unlisted);
        if (!first) return;
        _S.view = first.id; syncToURL(); render();
      };
    });
    const inp = document.getElementById("gl-search");
    if (inp) {
      inp.value = _S.q;
      inp.addEventListener("input", () => { _S.q = inp.value; syncToURL(); render(); });
      inp.addEventListener("keydown", e => {
        if (e.key === "Escape") { inp.value = ""; _S.q = ""; syncToURL(); render(); }
      });
    }
    window.addEventListener("hashchange", () => { if (!syncFromURL()) render(); });
    // Crossing the two-pane breakpoint redraws the Terms view in the other layout.
    const mq = window.matchMedia && window.matchMedia("(min-width: 900px)");
    if (mq && mq.addEventListener) mq.addEventListener("change", () => {
      if (_S.view === "terms" && _GL_STATE === "ready") render();
    });
    const start = () => {
      GL = window.EEPHUS_GLOSSARY || {};
      _GL_STATE = "ready";
      render();
    };
    if (window.EEPHUS_GLOSSARY) start();
    else {
      window.addEventListener("eephus-glossary-ready", start, { once: true });
      window.addEventListener("eephus-glossary-failed", () => {
        if (_GL_STATE !== "ready") { _GL_STATE = "failed"; render(); }
      });
      _GL_STATE = window.EEPHUS_GLOSSARY_FAILED ? "failed" : "loading";
      render();
    }
  }

  // The loading or failed box for the active view while data/glossary.json is
  // outstanding. The message is plain copy; Retry asks eephus-gl.js to fetch
  // again and puts the loader back up until it answers.
  function _paintGlState(el) {
    if (!el) return;
    const S = window.EephusState;
    if (_GL_STATE === "failed") {
      const msg = `The ${escapeHtml(LIB_NAME)} could not be loaded. Check your connection and try again.` +
        '<div style="margin-top:12px;"><button class="chip" type="button" id="gl-load-retry">Retry</button></div>';
      el.innerHTML = S ? S.html("failed", msg, "gl-load-state")
        : `<div class="state-message gl-load-state" role="alert">${msg}</div>`;
      const rb = document.getElementById("gl-load-retry");
      if (rb) rb.onclick = () => {
        const G = window.EEPHUS_GL;
        if (!G || !G.reload) { location.reload(); return; }
        _GL_STATE = "loading";
        render();
        G.reload();
      };
      return;
    }
    const msg = `Loading the ${escapeHtml(LIB_NAME)}...`;
    el.innerHTML = S ? S.html("loading", msg, "gl-load-state")
      : `<div class="state-message gl-load-state" role="status">${msg}</div>`;
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
// The Methodology prose, one part per piece the chapters assemble
// (renderMethodology). Text moves verbatim from the one-scroll view; the
// section headings sit one level under each chapter's h2.
function _methProseParts() {
  // Tiered $/WAR for the worked example, read from the live framework snapshot
  // (data/value_framework.js -> window.VALUE_FRAMEWORK) instead of re-hardcoded
  // prose: the $7.7M/$9.7M/$15.1M this sentence used to carry had rotted a full
  // config generation behind the served table (the _methAccuracyChart pattern).
  const _dpwT = ((window.VALUE_FRAMEWORK || {}).dollars_per_war || {}).tiered_mm || {};
  const _dpwF = v => (v == null || isNaN(Number(v)) ? null : "$" + Number(v).toFixed(2) + "M");
  const _dpwTxt = (_dpwF(_dpwT.lt_1) && _dpwF(_dpwT["1_to_2"]) && _dpwF(_dpwT["2plus"]))
    ? ` (about ${_dpwF(_dpwT.lt_1)} / ${_dpwF(_dpwT["1_to_2"])} / ${_dpwF(_dpwT["2plus"])} by WAR level)`
    : "";
  return {
    efv: `
    <h3 class="meth-h">How eFV is built <span class="meth-sub">the site's primary grade</span></h3>
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
`,
    consensus: `
    <h3 class="meth-h">How the consensus FV (eFV's prior) is built</h3>
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
`,
    arkmetrics: `
    <h3 class="meth-h">How the Arkmetrics are derived</h3>
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
`,
    example: `
    <div class="meth-eg-card">
      <div class="meth-eg-title">Worked example · how a grade becomes a dollar figure</div>
      <div class="meth-eg-row">An <b>${gTermLink("fv", "FV")} 60</b> shortstop: the FV→WAR anchor maps the grade to a per-year WAR expectation, the position multiplier nudges it for the up-the-middle profile, and the seven cost-controlled years are priced at the tiered ${gTermLink("dpw_tier", "$/WAR")}${_dpwTxt} minus the league-min-plus-arb cost basis, then probability-weighted across debut and bust outcomes and discounted to present value.</div>
      <div class="meth-eg-row">The result is the published ${gTermLink("surplus_value", "surplus value")} on that player's card. A higher ${gTermLink("dvm_plus", "$DvM+")} (faster-than-mean development) and stronger underlying rates (${gTermLink("k_pct", "K%")} / ${gTermLink("bb_pct", "BB%")}, ${gTermLink("ops_plus", "OPS+ vs lvl")}) lift the expectation within the FV band.</div>
      <div class="meth-eg-note">Illustrative - each player's card carries their own current figure, which moves with the FV→WAR table and the $/WAR market.</div>
    </div>
`,
    surplus: `
    <h3 class="meth-h">Surplus value - the economic model</h3>
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
`,
    aggregation: `
    <h3 class="meth-h">Aggregation - player level to farm level</h3>
    <p>Roll-ups are explicit, not implied. Org surplus is the sum of its active prospects' per-player
    surplus dollars (the authoritative engine aggregate, <code>_active_surplus_net_mm</code>); the farm
    list, the detail Surplus tile, and the Finances tab all read that one number. DvM+ / ToolDvM+
    aggregate per-tool development across the org's actives with acquisitions nullified (so a trade
    doesn't read as development) and graduations not subtracted (so promoting a star doesn't read
    as a loss). The "+" indices (DvM+, RPS+, SC+, OrgSur+) are all built to the wRC+/OPS+ convention - 
    100 = the relevant mean, ±10 ≈ one standard deviation - so they share one mental scale.</p>
`,
    analogue: `
    <h3 class="meth-h">Where the Arkmetrics sit vs public metrics</h3>
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
`,
    farm: `
    <h3 class="meth-h">Farm-system grades - how the org letter is built</h3>
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
`,
    faq: `
    <dl class="meth-dl">
      <dt>Why a consensus instead of one source?</dt>
      <dd>Averaging cancels idiosyncratic source error, and the measured edge is two-legged: on resolved cohorts the blend separates future contributors from non-contributors better than any single input (the AUC leg clears its floor), while on ordering realized WAR the gap to its best input sits inside the noise floor the backtest can resolve. Blending buys discrimination, not ordering; the live legs and floors render in Source Comparison. Per-source edges are small and unstable year to year, which is why the blend stays at equal weights rather than chasing them.</dd>
      <dt>How are sources weighted?</dt>
      <dd>Equally: every source votes at exactly 1.0. An accuracy-weighted blend (per-source weights from measured track records, shrunk toward equal and clamped) shipped in June 2026 and was reverted on 2026-07-25, when a hardened forward-chained re-measurement showed its edge was smaller than the test could resolve (d&rho; -0.0012 vs a minimum detectable effect of 0.0068) - the weights were unearned, so they came off. Only two of eight outlets even have resolvable outcome history. The interactive in Value and surplus lets you test any weighting yourself.</dd>
      <dt>How often does it update?</dt>
      <dd>Grades, Arkmetrics, farm grades, and the backtest refresh monthly; transactions, IL, roster status, debuts, and trades refresh daily. Each board stamps its own cadence.</dd>
      <dt>What's the track record - and its limits?</dt>
      <dd>The evaluation window spans seven preseason base years (2017-2023): the 2017-2020 cohorts are fully resolved while 2021-2023 are still accruing WAR, and cumulative WAR is censored at today. Top FV tiers stay thin (n≈40-70), so their rates move on a few outcomes. The Source Comparison area lists sample sizes and these caveats in full rather than headlining an inflated number.</dd>
    </dl>
`,
  };
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
// THE HEADLINE IS ONE KEY (owner answer FP3-1, 2026-09-25). The headline moved
// from the vintage-matched frame vm1 to the timing-pinned frame vm2, and no
// renderer on this view names a frame of its own: the hero, the bars, the star,
// the share card and the caveat all read accuracy.head_to_head_verdict and
// follow its `basis` to the accuracy block it was computed on. An artifact with
// no verdict renders no head-to-head rather than an older frame's numbers.
function _hhVerdict(bt) {
  return (bt && bt.accuracy && bt.accuracy.head_to_head_verdict) || null;
}

function _hhBlock(bt) {
  const hh = _hhVerdict(bt);
  const acc = bt && bt.accuracy;
  return (hh && hh.basis && acc && acc[hh.basis]) || null;
}

// The frame's name in copy, from the verdict's own frame_version.
function _hhFrameName(hh) {
  return (hh && hh.frame_version === "vm2") ? "vintage-matched, timing-pinned" : "vintage-matched";
}

function _hhStarRater(bt) {
  const hh = _hhVerdict(bt);
  const blk = _hhBlock(bt);
  if (!hh || hh.resolvable !== true || !blk) return null;
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
// chart rather than the uncorrected one. Since 2026-09-25 that block is found
// through head_to_head_verdict.basis (_hhBlock), never named here.
function _methAccuracyChart(bt) {
  const acc = _hhBlock(bt);
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
  const hhStar = _hhVerdict(bt);
  const starNote = `<p class="meth-sub">★ marks a grader only where its gap clears a published noise floor. ${spStar
    ? "The Spearman gap clears its floor."
    : (hhStar && hhStar.resolvable === false)
      ? "The Spearman gap does not, so no bar is starred."
      : "No floor is published for the Spearman gap here, so no bar is starred."} No AUC bar is starred: whether any gap between eFV and one source clears its floor, on either leg, is read in the per-source table below, after a correction for testing several sources at once.</p>`;
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
  const hh = _hhVerdict(bt);
  let verdict;
  if (x && x.spearman != null && c && c.spearman != null) {
    const f3 = v => (v == null ? "-" : v.toFixed(3));
    const n = Number((hh && hh.n) || (x && x.n) || 0).toLocaleString();
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
    const pubs = [["PROSPX consensus", c, "prospx_consensus"], ["MLB Pipeline", mlb, "mlb_pipeline"], ["FanGraphs", fg, "fangraphs"]]
      .filter(pr => pr[1] && pr[1].spearman != null);
    const bestPub = pubs.length
      ? pubs.reduce((a, b) => (b[1].spearman > a[1].spearman ? b : a)) : null;
    const lead = bestPub ? (x.spearman - bestPub[1].spearman) : null;
    const ahead = (lead != null && lead > 0);
    // RPR11: the lead is against the best source, so the floor quoted beside it
    // and the call it decides are that pair's, not consensus's (_hhPairFloor).
    const bestFloor = bestPub ? _hhPairFloor(bt, bestPub[2]) : null;
    const resolvable = !!(bestFloor && bestFloor.resolvable === true);
    // A gap that clears the uncorrected floor but not the Holm one misses the
    // Holm floor; quote the floor it actually misses.
    const missFloor = !bestFloor ? null
      : (bestFloor.clearsUncorrected && bestFloor.holmFloor != null) ? bestFloor.holmFloor : bestFloor.mde95;
    const cls = (ahead && resolvable) ? "is-good" : "";
    const bestTxt = bestPub
      ? `${f3(bestPub[1].spearman)} for the best of them, ${escapeHtml(bestPub[0])}` : "";
    const head = (lead == null)
      ? `eFV orders realized WAR at Spearman ${f3(x.spearman)}`
      : (ahead && resolvable)
        ? `eFV orders realized WAR ahead of every source measured here, by a margin this backtest can resolve: Spearman ${f3(x.spearman)} against ${bestTxt}, a lead of +${lead.toFixed(3)} against a floor of ${f3(bestFloor && bestFloor.mde95)}`
        : ahead
          ? `eFV orders realized WAR ahead of every source measured here, but not by enough to call it: Spearman ${f3(x.spearman)} against ${bestTxt}, a lead of +${lead.toFixed(3)} that does not clear the ${f3(missFloor)} floor this backtest publishes for that pair`
          : `eFV and the best source measured here are indistinguishable: Spearman ${f3(x.spearman)} for eFV against ${bestTxt}, a ${lead.toFixed(3)} point estimate, so no ordering claim is made in either direction`;
    const rowTxt = pubs.map(pr => `${f3(pr[1].spearman)} ${escapeHtml(pr[0])}`).join(", ");
    verdict = `<p class="meth-verdict ${cls}">Out of sample and leakage-free, on the ${n} players eFV and the boards both grade, ${head}. The full row: eFV ${f3(x.spearman)}, ${rowTxt}. A wider gap you may have seen quoted compares eFV on its own rows against the boards on all of theirs, and about half of that one is the row difference rather than the ordering.</p>`;
  } else {
    verdict = `<p class="meth-verdict">On the common set of ${bt.accuracy.common_n.toLocaleString()} players, the consensus is competitive with its inputs but does not lead on every metric (reported as measured, not cherry-picked).</p>`;
  }
  const nRows = (hh && hh.n) || (acc.xfv && acc.xfv.n) || null;
  return `<div class="meth-chart meth-accuracy">
    <div class="meth-chart-title">Head-to-head predictive accuracy <span class="meth-sub">same players, same outcome, same window, same vintage, ${escapeHtml(_hhFrameName(hh))} frame${nRows ? ` &middot; n=${Number(nRows).toLocaleString()}` : ""}</span></div>
    ${sp}${au}${starNote}${verdict}
  </div>`;
}

// PER-SOURCE CELLS, HOLM-CORRECTED (owner answer FP3-3, 2026-09-25). eFV against
// each source on each leg, on the headline frame's rows. The family, its size and
// its alpha are read from the artifact (head_to_head_vs_sources.holm), and a cell
// prints a verdict word only when the artifact gives it one, which it does only
// for a cell that survives the correction; every other cell prints its interval
// alone. Nothing is computed here.
function _methPerSourceCells(bt) {
  const hh = _hhVerdict(bt);
  const vs = bt && bt.accuracy && bt.accuracy.head_to_head_vs_sources;
  if (!hh || !vs || !vs.sources || !vs.holm || vs.basis !== hh.basis) return "";
  const h = vs.holm;
  const f4 = v => (v == null || isNaN(Number(v)) ? "-" : Number(v).toFixed(4));
  const s4 = v => (v == null || isNaN(Number(v)) ? "-" : (Number(v) > 0 ? "+" : "") + Number(v).toFixed(4));
  const s3 = v => (v == null || isNaN(Number(v)) ? "-" : (Number(v) > 0 ? "+" : "") + Number(v).toFixed(3));
  const cell = leg => {
    if (!leg) return `<td>-</td><td>-</td><td>-</td>`;
    const ci = Array.isArray(leg.ci95) ? `<br><span class="meth-sub" style="white-space:nowrap;">CI95 ${s3(leg.ci95[0])} to ${s3(leg.ci95[1])}</span>` : "";
    const fl = leg.holm && leg.holm.mde95_holm != null ? f4(leg.holm.mde95_holm) : "-";
    const word = leg.verdict
      ? `<span class="${leg.delta > 0 ? "sacc-verdict-win" : "sacc-verdict-null"}">${escapeHtml(leg.verdict)}</span>`
      : `<span class="meth-sub">interval only</span>`;
    return `<td>${s4(leg.delta)}${ci}</td><td>${fl}</td><td>${word}</td>`;
  };
  const labels = { prospx_consensus: "PROSPX consensus", mlb_pipeline: "MLB Pipeline", fangraphs: "FanGraphs" };
  const fam = (h.family || []).map(k => {
    const [r, m] = String(k).split(".");
    return `${labels[r] || r} ${m === "auc" ? "AUC" : "Spearman"}`;
  }).join(", ");
  const rows = Object.keys(vs.sources).map(r => {
    const c = vs.sources[r] || {};
    return `<tr><td>${escapeHtml(c.label || labels[r] || r)}</td>${cell(c.spearman)}${cell(c.auc)}</tr>`;
  }).join("");
  const alpha = h.alpha != null ? Number(h.alpha).toString() : "-";
  return `<div class="meth-chart scx-per-source">
    <div class="meth-table-title">eFV against each source, corrected for testing several at once <span class="meth-sub">${escapeHtml(_hhFrameName(hh))} frame, n=${Number(vs.n || 0).toLocaleString()}</span></div>
    <div class="table-scroll-x"><table class="meth-table">
      <thead><tr><th rowspan="2">Source</th><th colspan="3" style="text-align:center;">Ordering (Spearman)</th><th colspan="3" style="text-align:center;">Contributor AUC</th></tr>
      <tr><th>eFV minus source</th><th>Floor after Holm</th><th>Reading</th><th>eFV minus source</th><th>Floor after Holm</th><th>Reading</th></tr></thead>
      <tbody>${rows}</tbody>
    </table></div>
    <p class="meth-note">One family of ${Number(h.k || 0)} tests (${escapeHtml(fam)}), Holm step-down at a family alpha of ${escapeHtml(alpha)}, one-sided on the gap over its bootstrap spread, fixed before any cell was read. A cell carries a verdict only when its gap survives the correction; the rest are read as their interval alone. The PROSPX consensus Spearman cell is the headline above and also needs the headline's own floor to agree. Every figure is read from the backtest artifact.</p>
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
// nightly-updating counterpart is the calibration monitor on the Calibration
// leaf. Shows the current tripwire status inline once the shared reliability
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
    <div class="meth-find-label">eFV publishes its own live calibration - <a href="#view=calibration">see the monitor in Calibration</a></div>
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
  const frozenChip = c.tiers_frozen && c.tiers_frozen.chip
    ? ` <span class="sacc-chip-warn" title="${escapeHtml(c.tiers_frozen.until || "")}">${escapeHtml(c.tiers_frozen.chip)}</span>` : "";
  return `<div class="meth-table-wrap">
    <div class="meth-table-title"><span class="meth-legend-swatch" style="background:${_raterMeta(rater).color};"></span>${escapeHtml(_raterMeta(rater).label)} <span class="meth-sub">n=${c.n} · ${c.n_debuted} debuted</span>${frozenChip}</div>
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
  const hh = _hhVerdict(bt);
  const fmt = v => (v == null || isNaN(Number(v)) ? "-" : Number(v).toFixed(3));
  if (!hh || hh.delta == null || hh.mde95 == null) {
    return "<strong>The head-to-head is a point estimate.</strong> No floored verdict is loaded, so no ordering claim is made.";
  }
  const n = hh.n != null ? `the same ${Number(hh.n).toLocaleString()}` : "identical";
  const fr = escapeHtml(_hhFrameName(hh));
  const d = Number(hh.delta);
  const sd = (d > 0 ? "+" : "") + d.toFixed(3);
  if (hh.resolvable === true && hh.xfv_beats === true) {
    return `<strong>eFV's head-to-head lead clears its floor.</strong> On ${n} ${fr} rows eFV leads PROSPX consensus by ${sd} against a noise floor of ${fmt(hh.mde95)}.`;
  }
  if (hh.resolvable === true) {
    return `<strong>eFV trails the consensus by a margin that clears its floor.</strong> On ${n} ${fr} rows eFV minus PROSPX consensus is ${sd} against a noise floor of ${fmt(hh.mde95)}.`;
  }
  return `<strong>The head-to-head does not resolve.</strong> On ${n} ${fr} rows eFV minus PROSPX consensus is ${sd} against a noise floor of ${fmt(hh.mde95)}, so neither grade is called the winner.`;
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
    anat(`<span style="font-family:var(--font-mono);font-size:12px;color:var(--text-violet);">$DvM+ 110</span>`, "dvm_plus",
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
      "Projected MLB-arrival year: the model's year from level, age, performance and FV, averaged with FanGraphs' published ETA where FanGraphs lists one."),
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
    anat(`<span style="font-family:var(--font-mono);font-size:13px;color:var(--text-gold);">⇄</span>`, "trade",
      "Trade markers stamp cross-org moves at the FV the league assigned on the trade date."),
  ].join("");

  const farmAnatomy = [
    anat(`<span style="font-family:var(--font-mono);font-size:12px;color:var(--text-secondary);">A+ tree</span>`, "farm_report_card",
      "The org letter grade is a weighted tree, value-led: a Value branch (aggregate risk-adjusted surplus), then MLB Production, Development, and Acquisition Strategy, each built from auditable leaves."),
    anat(`<span style="font-family:var(--font-mono);font-size:12px;color:var(--text-violet);">DvM+ 112</span>`, "dvm_plus",
      "Development vs Mean - how fast the org grows the FV of prospects it already had (acquisitions nullified), 100 = league mean."),
    anat(`<span style="font-family:var(--font-mono);font-size:12px;color:var(--neon-cyan);">ToolDvM+ 108</span>`, "tools_dvm_plus",
      "The same development idea applied per tool, weighted by what each position needs."),
    anat(`<span style="font-family:var(--font-mono);font-size:12px;color:var(--up);">OrgSur+ 121</span>`, "sur_plus",
      "Org-level capital efficiency - WAR and contract surplus per dollar spent, scaled to 100 = league mean."),
  ].join("");

  el.innerHTML = `
  <div class="guide-wrap">
    <p class="guide-intro">Every number on the site resolves to a ${escapeHtml(LIB_NAME)} entry. This page labels the elements you'll see on a player card, the FV history chart, and a farm-system page, then shows how the metrics build on one another. Click any underlined term for its definition.</p>

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
    <div class="gx-surplus-final">Published surplus value <b>${_fmtMM2(published)}</b><div class="gx-surplus-note">The published figure additionally probability-weights the outcome distribution and discounts future years at ${vf.dpw_path ? `${(Number(vf.dpw_path.nominal_rate) * 100).toFixed(2)}%/yr nominal, with each season's win priced on the one written path growing ${(Number(vf.dpw_path.g_ref) * 100).toFixed(2)}%/yr` : (vf.discount_rate != null ? `${(Number(vf.discount_rate) * 100).toFixed(0)}%/yr` : "the platform rate")}, so it differs slightly from the flat framework walk above.</div></div>`);
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
  <h3 class="meth-h">Interactive - manipulate the models</h3>
  <p class="meth-note">These run on the live framework values. Move the inputs to see how a scouting grade, a source-weighting scheme, and the surplus walk respond.</p>

  <div class="gx-card">
    <div class="gx-card-title">The 20-80 scale as a distribution</div>
    <div class="gx-card-body gx-2col">
      <div>
        <label class="gx-label" for="gx-grade-in">Grade <b id="gx-grade-val">60</b></label>
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
        <label class="gx-label" for="gx-surplus-fv">FV <b id="gx-surplus-fvval">55</b></label>
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
// Calibration leaf renders the full monitor; the Source Comparison view shows
// the tripwire status on its calibration cross-link tile. One in-flight guard,
// one cached payload; the resolve re-renders whichever consumer view is
// active. Diagnostic only; a failed fetch or absent artifact simply drops the
// dependent sub-blocks - it is dark-launched, so the dev artifact is a stale
// vintage that the canonical box regenerates nightly.
function _loadReliability() {
  if (_S.reliability || _S.relLoading) return;
  _S.relLoading = true;
  const rerender = () => {
    if (_S.view === "calibration") renderCalibration();
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
// the model registry for the ledger tile, fetched by the click itself through
// _loadRegistryThen), never hardcoded, so the card can
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
// Methods chapter "Our tables vs the industry's" (#industry-comparison).
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
  const drate = vf.dpw_path ? `${_rn(Number(vf.dpw_path.nominal_rate) * 100, 2)}%/yr nominal`
    : ((vf.discount_rate != null) ? `${_rn(Number(vf.discount_rate) * 100, 0)}%/yr` : "the platform rate");
  const blockE = `<div class="meth-table-wrap">
    <div class="meth-table-title">The economics layer <span class="meth-sub">expectations, NPV, and a moving $/WAR</span></div>
    <p class="meth-note"><strong>A price is an expectation, not a median.</strong> The median outcome of a low-tier prospect is a bust worth nothing, so a median-target price floors at $0 and calls every lottery ticket free. The trade engine consumes surplus as a price, and a price is a mean: since the EV reframe the correction map targets the conditional mean and the $0 floor is gone. The calibration receipt is <a href="/data/surplus_backtest_real.json" target="_blank" rel="noopener">surplus_backtest_real.json</a>, also rendered on the Surplus value entry in Terms.</p>
    <p class="meth-note"><strong>A deferred dollar is not a dollar.</strong> Contract legs are compared on NPV at ${drate}, so a heavily deferred sticker deflates to the liability it actually is before any comparison runs. The schedules live in the deferral ledger (<a href="/data/deferrals.json" target="_blank" rel="noopener">deferrals.json</a>); the Ohtani contract is its canonical entry.</p>
    <p class="meth-note"><strong>The market re-prices a win every winter.</strong>${dpwLine} Served prospect dollars ride the checksummed <code>clemens_2026</code> valuation set with the FA-implied re-anchor disabled, so a single hot winter cannot silently reflate every board.</p>
  </div>`;

  return `<div class="source-comp-wrap">
    <div class="source-comp-eyebrow"><span class="scx-dot"></span>Our tables vs the industry's · same names, different quantities</div>
    <p class="meth-note">Public prospect math mostly fails on units, not opinions. Each block below names one trap, shows the arithmetic shape, and points at the committed artifact; the per-model numbers live in the entry receipts under Terms.</p>
    <div class="meth-tables">${blockA}${blockB}${blockC}${blockD}${blockE}</div>
  </div>`;
}

// The Methods chapters (LIBRARY_5), in reading order. Each chapter is an h2
// with its id; the rail (900 px and wider) and the chapter select (narrower)
// are built from this list. A function, not a const, so a render that runs
// before this line is reached never meets a temporal dead zone.
function _methChapters() {
  return [
    { id: "meth-efv", label: "eFV" },
    { id: "meth-consensus", label: "Consensus FV" },
    { id: "meth-arkmetrics", label: "Arkmetrics" },
    { id: "meth-value", label: "Value and surplus" },
    { id: "meth-farm", label: "Farm grade" },
    { id: "industry-comparison", label: "Our tables vs the industry's" },
    { id: "meth-faq", label: "FAQ" },
  ];
}

// One pixel lamp per rail entry, drawn with the px-lamp tokens of
// assets/site.css: unlit (lo) on every chapter but the current one (lt).
function _methRailLamp() {
  return '<svg class="px-lamp meth-rail-lamp" width="8" height="8" viewBox="0 0 8 8" aria-hidden="true">'
    + '<rect class="lo" x="0" y="0" width="8" height="8"/></svg>';
}

// The model registry, fetched only when a reader asks for the Generate GFX
// card (its ledger tile counts the verdicts); the Methodology view itself
// never requests it. Every caller waiting on the one fetch runs on arrival.
function _loadRegistryThen(cb) {
  if (_S.registry) { cb(); return; }
  (_S.regWaiters = _S.regWaiters || []).push(cb);
  if (_S.regLoading) return;
  _S.regLoading = true;
  const done = j => {
    _S.registry = j || { __error: true };
    _S.regLoading = false;
    const waiting = _S.regWaiters || [];
    _S.regWaiters = [];
    waiting.forEach(f => f());
  };
  fetch("/data/model_registry.json", { cache: "no-cache" })
    .then(r => (r.ok ? r.json() : null))
    .then(done)
    .catch(() => done(null));
}

function renderMethodology() {
  const el = document.getElementById("methodology-body");
  if (!el) return;
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
  const P = _methProseParts();
  const prose = s => `<div class="meth-prose">${s}</div>`;
  const inner = {
    "meth-efv": prose(P.efv + `    <p>Every model on the site, with its verdict and its eval artifact, is listed on the <a href="/models/">Models</a> page.</p>\n`),
    "meth-consensus": prose(P.consensus + `    <p>The upstream data sources and the credit each publisher is owed are on the <a href="/sources/">Data Sources</a> page. The public data catalog, every file the site publishes, sits on the same page.</p>\n`),
    "meth-arkmetrics": prose(P.arkmetrics),
    "meth-value": prose(P.example + P.surplus + P.aggregation + P.analogue) + _methInteractivesHTML(),
    "meth-farm": prose(P.farm),
    "industry-comparison": _methIndustryHTML(),
    "meth-faq": prose(P.faq),
  };
  const chs = _methChapters();
  const rail = `<nav class="meth-rail" aria-label="Chapters"><ol>${chs.map(c =>
    `<li><a href="#view=methodology&amp;ch=${c.id}" data-meth-go="${c.id}">${_methRailLamp()}<span>${escapeHtml(c.label)}</span></a></li>`).join("")}</ol></nav>`;
  const select = `<label class="meth-chsel"><span class="meth-chsel-k">Chapter</span><select id="meth-chsel" aria-label="Go to a chapter">${chs.map(c =>
    `<option value="${c.id}">${escapeHtml(c.label)}</option>`).join("")}</select></label>`;
  const chapters = chs.map(c => `<section class="meth-chapter" data-meth-ch="${c.id}">
    <h2 class="meth-chapter-h" id="${c.id}">${escapeHtml(c.label)}</h2>
    ${inner[c.id]}
  </section>`).join("");
  el.innerHTML = printHead + toolbar
    + `<div class="meth-chaptered">${rail}<div class="meth-chapters">${select}${chapters}</div></div>`;
  if (window.EEPHUS_GL) window.EEPHUS_GL.wire(el);
  // Ad-card GFX: spec built at click time from the loaded artifacts; the
  // registry is fetched on this click and the card opens once it answers. A
  // click before the scoreboard resolves (or with the engine absent) is a
  // clean no-op.
  const gfxBtn = document.getElementById("gl-meth-gfx");
  if (gfxBtn) gfxBtn.onclick = () => _loadRegistryThen(() => {
    const spec = _methAdGfxSpec();
    if (spec && window.EEPHUS_GFX) window.EEPHUS_GFX.open(spec);
  });
  // Populate the interactives' initial state, then wire the chapters (a
  // deep-link scroll must follow the widgets' own height).
  _gx2080(); _gxConsensus(); _gxSurplus();
  _methWireChapters(el);
}

// The rail and the select move the reader between chapters without touching
// the view hash; an IntersectionObserver lights the lamp of the chapter the
// reader is in (the last chapter whose heading has crossed the top quarter
// of the viewport). Each render replaces the markup, so the observer is
// rebuilt with it.
function _methWireChapters(el) {
  const chs = _methChapters();
  const go = id => {
    const h = document.getElementById(id);
    if (h) h.scrollIntoView({ behavior: "smooth", block: "start" });
  };
  el.querySelectorAll("[data-meth-go]").forEach(a => {
    a.onclick = e => { e.preventDefault(); go(a.dataset.methGo); };
  });
  const sel = document.getElementById("meth-chsel");
  if (sel) sel.onchange = () => go(sel.value);
  const light = () => {
    const line = window.innerHeight * 0.25;
    let cur = chs[0].id;
    for (const c of chs) {
      const h = document.getElementById(c.id);
      if (h && h.getBoundingClientRect().top <= line) cur = c.id;
    }
    el.querySelectorAll("[data-meth-go]").forEach(a => {
      const on = a.dataset.methGo === cur;
      if (on) a.setAttribute("aria-current", "location"); else a.removeAttribute("aria-current");
      const r = a.querySelector(".meth-rail-lamp rect");
      if (r) r.setAttribute("class", on ? "lt" : "lo");
    });
    if (sel && sel.value !== cur) sel.value = cur;
  };
  if (_S.methObs) _S.methObs.disconnect();
  if ("IntersectionObserver" in window) {
    _S.methObs = new IntersectionObserver(light, { rootMargin: "0px 0px -75% 0px", threshold: [0, 1] });
    el.querySelectorAll(".meth-chapter, .meth-chapter-h").forEach(n => _S.methObs.observe(n));
  }
  light();
  // A chapter deep link scrolls there on each render for a moment, so the
  // late artifact renders above it cannot push it off screen.
  if (_S.methCh) {
    const h = document.getElementById(_S.methCh);
    if (h) h.scrollIntoView({ block: "start" });
    if (!_S.methChTimer) _S.methChTimer = setTimeout(() => { _S.methCh = null; _S.methChTimer = null; }, 2500);
  }
}

// Evidence > Calibration (LIBRARY_5): the two measurements that left the
// Methodology view, the live calibration monitor and what an eFV grade is
// worth. Each fetch re-renders this leaf on arrival; until both answer the
// leaf shows the shared loading box, and if neither renders it says so.
function _loadValuationCurve() {
  if (_S.valcurve || _S.vcLoading) return;
  _S.vcLoading = true;
  // eFV valuation curve: the per-tier published-vs-model-vs-live
  // worth-of-a-grade artifact (efv_export._valuation_curve). Diagnostic only;
  // absent or errored, the section simply does not render.
  const rerender = () => { if (_S.view === "calibration") renderCalibration(); };
  fetch("/data/xfv_valuation_curve.json", { cache: "no-cache" })
    .then(r => (r.ok ? r.json() : null))
    .then(j => { _S.valcurve = j || { __error: true }; rerender(); })
    .catch(() => { _S.valcurve = { __error: true }; rerender(); });
}

function renderCalibration() {
  const el = document.getElementById("calibration-body");
  if (!el) return;
  _loadReliability();
  _loadValuationCurve();
  const body = _methReliabilityHTML() + _methValuationCurveHTML();
  if (body) {
    el.innerHTML = body;
    if (window.EEPHUS_GL) window.EEPHUS_GL.wire(el);
    return;
  }
  const S = window.EephusState;
  const waiting = !_S.reliability || !_S.valcurve;
  const msg = waiting ? "Loading the calibration tables..." : "The calibration tables could not be loaded.";
  el.innerHTML = S ? S.html(waiting ? "loading" : "failed", msg, "gl-cal-state")
    : `<div class="state-message gl-cal-state" role="status">${msg}</div>`;
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
// The tripwire as one lamp row (LIBRARY_5): one lamp per tenth of the drift
// threshold, lit up to the bust-bucket ECE, so ten lit lamps reach the
// threshold. The row runs ten lamps, longer when the ECE is over the
// threshold; a rule marks the threshold, and lamps past it take the second
// lamp colour. Every value is read from the reliability artifact's tripwire.
function _relTripLamp(tw) {
  const ece = Number(tw.bust_ece), thr = Number(tw.threshold);
  if (!(thr > 0) || isNaN(ece)) return "";
  const lit = Math.max(0, Math.round((ece / thr) * 10));
  const n = Math.max(10, lit), C = 10, G = 3, R = 4, H = 14;
  const x = i => i * (C + G) + (i >= 10 ? R : 0);
  let cells = "";
  for (let i = 0; i < n; i++) {
    const cls = i < lit ? (i < 10 ? "lt" : "lb") : "lo";
    cells += `<rect class="${cls}" x="${x(i)}" y="0" width="${C}" height="${H}"/>`;
  }
  const rx = 10 * (C + G);
  cells += `<rect class="lr" x="${rx}" y="0" width="2" height="${H}"/>`;
  const W = x(n - 1) + C;
  const f3 = v => v.toFixed(3);
  return `<div class="px-lamp-wrap meth-trip-lamp"><svg class="px-lamp" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" role="img"`
    + ` aria-label="Bust-bucket calibration error ${f3(ece)} against a drift threshold of ${f3(thr)}: ${lit} lamps lit, ten reach the threshold">${cells}</svg></div>`
    + `<div class="px-lamp-key"><span><i class="px-lk t"></i>one lamp per tenth of the threshold (${f3(thr)})</span>`
    + (lit > 10 ? `<span><i class="px-lk b"></i>past the threshold</span>` : "")
    + `<span>${lit} lit; the rule is the threshold</span></div>`;
}
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
        : ", so no drift is flagged this run."}</div>${_relTripLamp(tw)}`;
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
    <p class="meth-note">What an eFV grade is worth: the model's own surplus, WAR and star odds per tier, against the published FanGraphs 2026 anchor and the live board${gen}. Surplus is $M over the ${escapeHtml(_windowLabel(vc.war_window))}, priced under the ${escapeHtml(String(vc.valuation_set || "production"))} valuation set. That is a different window from the club control window on the MLB Projections board's veteran rows, which prices only the seasons a salary is known or projected for; its prospect rows print each prospect's eFV surplus on this window.${starDefNote}</p>
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

// THE FLOOR BELONGS TO ONE PAIR (RPR11, 2026-10-02). The hero printed eFV
// against the best public source, which on the vm2 frame is MLB Pipeline
// (0.393 against 0.398), and then attached head_to_head_verdict's 0.030. That
// floor is the E_refit floor of eFV against PROSPX CONSENSUS, carried from vm1;
// the eFV against MLB Pipeline floor is the in-run E_cond 0.0235 in
// head_to_head_vs_sources. So the sentence floor-checked one pair with
// another pair's floor. This returns the floor of eFV against `key` on the
// headline rows, read from the artifact: the consensus pair from
// head_to_head_verdict (its Holm cell also needs that verdict to agree), any
// other source from its own Spearman cell, whose verdict word exists only when
// the cell survives the Holm family. A cell on another basis, or one with no
// floor, returns null and the caller prints no floor rather than a wrong one.
function _hhPairFloor(bt, key) {
  const hh = _hhVerdict(bt);
  if (!hh) return null;
  if (!key || key === "prospx_consensus") {
    if (hh.mde95 == null) return null;
    return {
      mde95: hh.mde95,
      estimator: hh.mde95_estimator || hh.estimator || "",
      resolvable: hh.resolvable === true,
      carriedFrom: hh.mde95_status === "carried" ? String(hh.mde95_carried_from || "earlier") : null,
      clearsUncorrected: null,
      holmFloor: null,
    };
  }
  const vs = bt && bt.accuracy && bt.accuracy.head_to_head_vs_sources;
  if (!vs || vs.basis !== hh.basis || !vs.sources) return null;
  const leg = vs.sources[key] && vs.sources[key].spearman;
  if (!leg || leg.mde95 == null) return null;
  return {
    mde95: leg.mde95,
    estimator: leg.mde95_estimator || "",
    resolvable: !!leg.verdict,
    carriedFrom: leg.mde95_status === "carried" ? String(leg.mde95_carried_from || "earlier") : null,
    clearsUncorrected: leg.clears_e_cond_floor === true,
    holmFloor: (leg.holm && leg.holm.mde95_holm != null) ? leg.holm.mde95_holm : null,
  };
}

// The floor clause for eFV against `key` (PROSPX consensus when omitted). It
// ends the sentence; the caller adds the "unresolved, not a win" reading.
function _hhFloorClause(bt, key) {
  const hh = _hhVerdict(bt);
  const fl = hh ? _hhPairFloor(bt, key) : null;
  if (!fl) return ".";
  // f3 is declared `const` INSIDE four other functions and is NOT module-scope.
  // Referencing it here threw ReferenceError, which took out _methHeroBanner and
  // with it the whole source-comparison view - the page rendered nothing at all.
  // A local formatter is the fix; do not reach for the outer ones.
  const fmt = v => (v == null || isNaN(Number(v)) ? "-" : Number(v).toFixed(3));
  const est = fl.estimator ? ` ${escapeHtml(fl.estimator)}` : "";
  // A floor carried from an earlier frame says so where it is printed.
  const carried = fl.carriedFrom
    ? ` (carried from the ${escapeHtml(fl.carriedFrom)} frame, not re-measured on this one)` : "";
  const holm = fl.holmFloor != null;
  if (fl.resolvable) {
    return `, clearing its${est} noise floor of ${fmt(fl.mde95)}${carried}${holm ? " and the correction for testing several sources at once" : ""}.`;
  }
  if (fl.clearsUncorrected && holm) {
    return ` that clears its${est} noise floor of ${fmt(fl.mde95)} but not the ${fmt(fl.holmFloor)} floor after the correction for testing several sources at once.`;
  }
  return ` that does NOT clear its${est} noise floor of ${fmt(fl.mde95)}${carried}.`;
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
  // FP3-1 (2026-09-25): the block is found through head_to_head_verdict.basis,
  // with no fallback to another frame's numbers.
  const p = _hhBlock(bt) || {};
  const x = p.xfv, c = p.prospx_consensus, fg = p.fangraphs, mlb = p.mlb_pipeline;
  if (!x || x.spearman == null) return "";
  const f3 = v => (v == null ? "-" : v.toFixed(3));
  const pubs = [["PROSPX consensus", c, "prospx_consensus"], ["MLB Pipeline", mlb, "mlb_pipeline"], ["FanGraphs", fg, "fangraphs"]]
    .filter(pr => pr[1] && pr[1].spearman != null);
  const bestPub = pubs.length ? pubs.reduce((a, b) => (b[1].spearman > a[1].spearman ? b : a)) : null;
  const lead = (bestPub && x.spearman != null) ? (x.spearman - bestPub[1].spearman) : null;
  // Read the floored verdict from the artifact rather than re-deriving one here.
  // Declared at function scope on purpose: the last time this file reached for a
  // helper that was only bound inside another function, the ReferenceError blanked
  // the entire source-comparison view and the suite stayed green because the
  // view-walk test accepted the empty state as a pass.
  const hhv = _hhVerdict(bt);
  // RPR11: the lead printed is against the best public source, so the floor and
  // its resolvability are that pair's (_hhPairFloor), never consensus's floor
  // beside another source's estimate.
  const bestKey = bestPub ? bestPub[2] : null;
  const bestFloor = hhv ? _hhPairFloor(bt, bestKey) : null;
  const consFloor = hhv ? _hhPairFloor(bt, "prospx_consensus") : null;
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
  const resolvable = !!(bestFloor && bestFloor.resolvable);
  const headline = (lead == null)
    ? "eFV grades prospects on what they actually <em>became</em>."
    : (ahead && resolvable)
      ? "eFV grades prospects on what they actually <em>became</em>, and out of sample it ranks ahead of every public source by a margin that clears our noise floor."
      : ahead
        ? "eFV grades prospects on what they actually <em>became</em>, and out of sample it ranks ahead of every public source - by a margin we still cannot call a win."
        : "eFV grades prospects on what they actually <em>became</em>, and out of sample it is statistically indistinguishable from the best public scouting grade.";
  const leadClause = (lead != null && bestPub)
    ? `, ${f3(x.spearman)} against ${f3(bestPub[1].spearman)} for the best public source (${escapeHtml(bestPub[0])}), a ${lead >= 0 ? "+" : ""}${lead.toFixed(3)} point estimate${_hhFloorClause(bt, bestKey)}`
    : _hhFloorClause(bt);
  // eFV has to beat PROSPX consensus (owner, 2026-09-24). When the best public
  // source is another rater, the consensus pair is stated too, with the floor
  // head_to_head_verdict publishes for it.
  // The verdict's own delta when it publishes one, so this figure matches the
  // head-to-head verdict printed further down the view.
  const consLead = (hhv && hhv.delta != null) ? Number(hhv.delta)
    : (c && c.spearman != null) ? (x.spearman - c.spearman) : null;
  const consClause = (lead != null && bestKey && bestKey !== "prospx_consensus" && c && c.spearman != null && consLead != null)
    ? ` Against PROSPX consensus, the grade eFV has to beat, it reads ${f3(x.spearman)} against ${f3(c.spearman)}, a ${consLead >= 0 ? "+" : ""}${consLead.toFixed(3)} point estimate${_hhFloorClause(bt, "prospx_consensus")}`
    : "";
  const printed = [lead != null ? bestFloor : consFloor, consClause ? consFloor : null].filter(Boolean);
  const unresolvedTail = printed.some(f => !f.resolvable)
    ? " We report a gap that does not clear its floor as unresolved, not as a win." : "";
  const verbPhrase = ahead ? "it grades ahead of every one of them" : "it lands level with the best of them";
  return `<div class="source-comp-hero">
    <div class="source-comp-hero-kicker">A different kind of Future Value</div>
    <h2 class="source-comp-hero-title">${headline}</h2>
    <p class="source-comp-hero-lede">Every public FV grade is an educated opinion about the future. eFV is a model trained on resolved outcomes and scored the honest way: leakage-free, forward-chained, on the same players, the same window AND the same vintage as the sources it is measured against. On ordering skill - how well a preseason grade tracks the WAR a prospect went on to produce - ${verbPhrase}${leadClause}${consClause}${unresolvedTail}</p>
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
    <p class="meth-note"><strong>What did not ship:</strong> the same 2026-07-23 program ran four more gated lanes - playing-time IL risk for projections, MiLB park neutralization, per-pitch-type stuff into PAL conversions, and college stuff into the college-to-pro translation - and none cleared its gate. Nothing from those lanes touches a served number. Every failure is ledgered with its committed eval artifact in <a href="/models/">the model ledger</a>; that ledger is the point.</p>
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
  const tierFrozen = blk.fv_tier_freeze && blk.fv_tier_freeze.chip
    ? ` <span class="sacc-chip-warn" title="${escapeHtml(blk.fv_tier_freeze.until || "")}">FV-tier rows ${escapeHtml(blk.fv_tier_freeze.chip)}</span>` : "";
  return `<div class="meth-table-wrap">
    <div class="meth-table-title">${escapeHtml(sideLabel)} <span class="meth-sub">eFV vs consensus, identical rows</span>${tierFrozen}</div>
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
    <p class="meth-note">Each row reads <strong>what each side produced at the same grade</strong>. Nothing here compares one source's grade to another's. The reference throughout is realized first-six-year WAR on ${_saccN(basis.n)} resolved prospects, with players who never reached the majors carried at zero so survivors are not the only thing being scored.</p>
    <div class="table-scroll-x"><table class="meth-table">
      <thead><tr><th>Grade band</th><th>Hitters n</th><th>Their WAR</th><th>Pitchers n</th><th>Their WAR</th><th>Gap</th><th>95% interval</th></tr></thead>
      <tbody>${rows.join("")}</tbody>
    </table></div>
    <p class="meth-note">Only the bands that resolve are listed; every other cell sits inside its own noise and is published as unresolved in <a href="/data/xfv_side_calibration_eval.json" target="_blank" rel="noopener">the artifact</a>.</p>
    <p class="meth-verdict">The consensus grades pitchers <strong>too high at the top</strong>, measured against outcomes: at consensus FV 55 the hitters produced ${f2((cons["55"] || {}).mean_war_hit)} WAR and the pitchers ${f2((cons["55"] || {}).mean_war_pit)}. That is not a bust-rate story, because almost every player in both cells reached the majors. The eFV V2 board starts from the consensus grade on each side and keeps its per-side order unless an admitted driver moves it, so this side gap now sits in the consensus V2 reads. The eFV rows measure the v1 grade map${j.generated_at ? ` as of ${escapeHtml(String(j.generated_at).slice(0, 10))}` : ""}: its FV 45 band <strong>under-grades</strong> pitchers by a measurable margin.</p>
    <p class="meth-note">The v1 pitcher forecast itself is close to unbiased${(f.P && f.P.bias_pred_minus_real != null) ? ` (${f2(f.P.bias_pred_minus_real)} WAR against ${f2((f.H || {}).bias_pred_minus_real)} for hitters)` : ""}: it expects pitchers to produce less, and one shared value curve then grades them lower. Method and the pre-registered decision rule: <code>docs/efv-2026-08-12/SIDE_CALIBRATION_GATE.md</code>.</p>
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
  if (!bt || bt.__error || !bt.accuracy || !_hhBlock(bt)) return null;
  const pooled = _hhBlock(bt);
  const hh = _hhVerdict(bt);
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
  if (au.length >= 2) panels.push({ title: "Discrimination · contributor AUC (none starred)", lo: 0.5, hi: 0.85, rows: au, star: false });

  const years = (bt.window && bt.window.years) || [];
  const span = years.length ? years[0] + "-" + years[years.length - 1] : "";
  const nCommon = (hh && hh.n) || x.n || null;
  const sgn3 = v => (v == null || isNaN(Number(v)) ? "-" : (Number(v) > 0 ? "+" : "") + Number(v).toFixed(3));
  const call = (hh && hh.delta != null && hh.mde95 != null)
    ? "eFV vs consensus " + sgn3(hh.delta) + ", floor " + f3(hh.mde95)
      + (hh.resolvable ? ", resolved" : ", not resolvable") + " · "
    : "";
  const note = "Every grader on the same rows, base year equal to the eFV decision year, "
    + _hhFrameName(hh) + " frame · " + call + "★ only where a gap clears a published floor";
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

// ---- eFV progress ledger (EV-00, docs/efv-v2/PROGRAM.md s5.3) ---------------
// The owner asked on 2026-09-24 to watch, on this page, whether the eFV redo is
// beating PROSPX consensus and the industry. The ledger artifact is written by
// efv_progress.py, append-only, and every number in it is copied from a named
// key of the backtest or the scoreboard. Nothing below computes a statistic:
// the renderers print the row's own numbers, and the verdict word is the
// row's. Same lazy idiom as _loadScoreboard; an absent artifact drops the
// section and never the view.
function _loadProgress() {
  if (_S.progress || _S.progressLoading) return;
  _S.progressLoading = true;
  const rerender = () => { if (_S.view === "source-comparison") renderSourceComparison(); };
  fetch("/data/efv_progress.json", { cache: "no-cache" })
    .then(r => (r.ok ? r.json() : null))
    .then(j => { _S.progress = j || { __error: true }; rerender(); })
    .catch(() => { _S.progress = { __error: true }; rerender(); });
}

// Frames a chart series may hold. Tilted frames never, whatever the artifact
// lists: they are timing, not skill (PROGRAM.md s7 item 1). vm2 is the EV-01
// timing-pinned vintage-matched frame, the headline since 2026-09-25 (owner
// answer FP3-1); vm1, the frame it replaced, is superseded and sits in the table
// only. vm_dev and lv_dev hold development reads of a v2 candidate (EV-09),
// drawn as hollow circles: spent frames, never a claim.
const _PROG_CHART_FRAMES = ["vm2", "vm_dev", "lv_dev", "lv_res", "vm_pros"];

function _progRows(prog) {
  return (prog && !prog.__error && Array.isArray(prog.rows)) ? prog.rows : [];
}

function _progSeriesRows(prog) {
  const allowed = ((prog && prog.chart && prog.chart.series_frames) || _PROG_CHART_FRAMES)
    .filter(f => _PROG_CHART_FRAMES.includes(f));
  return _progRows(prog).filter(r => r.role !== "tilted" && r.tilted !== true
    && r.role !== "secondary" && r.role !== "superseded" && allowed.includes(r.frame)
    && (!_progIsScreen(r) || _progScreenAdmitted(r))
    && _progConsLeg(r) && _progConsLeg(r).delta != null);
}

// A row appended by a fix to how eFV is scored (DS-01) or by a change of the
// headline frame (FP3-1), never by a model change. Drawn and labelled apart so a
// reader never takes it for progress.
function _progIsCorrection(prog, r) {
  const trig = (prog && Array.isArray(prog.correction_triggers)) ? prog.correction_triggers : ["harness_correction", "data_correction"];
  const fc = (prog && Array.isArray(prog.frame_change_triggers)) ? prog.frame_change_triggers : ["frame_change"];
  return !!(r && (trig.includes(r.trigger) || fc.includes(r.trigger)));
}

// "scoring correction", "data correction" or "frame change", from the row's own
// trigger. The raw trigger of a scoring-code correction reads "harness_correction"
// in the ledger, which stays untouched; the page names it in site copy.
function _progCorrectionName(r) {
  const t = String((r && r.trigger) || "correction");
  return (t === "harness_correction" ? "scoring correction" : t).replace(/_/g, " ");
}

// A row's note as the page prints it. The ledger keeps every row as written; two
// display-time readings apply (audit QREC06): a scoring-code correction opens
// "Scoring correction" in site copy, and a note written before the headline frame
// changed, saying the frame would become the headline on a condition, is marked
// as written and given the date the headline frame's own note carries.
function _progNoteText(prog, r) {
  let n = String((r && r.note) || "");
  n = n.replace(/^Harness correction\b/, "Scoring correction");
  const hf = prog && prog.frames && prog.headline_frame && prog.frames[prog.headline_frame];
  const m = /headline since (\d{4}-\d{2}-\d{2})/.exec((hf && hf.note) || "");
  if (m) n = n.replace(/becomes the headline once [^;.]+/g, p => `${p} (as written; headline since ${m[1]})`);
  return n;
}

function _progConsLeg(r) {
  return ((r && r.deltas && r.deltas.vs_prospx_consensus) || {}).spearman || null;
}

// Screening lab rows (EFV3 lane B s5, tools/efv_screen_lab.py): one development row
// per measured arm, model_id "efv_v2_screen:wave<n>:<candidate>:<side>". They sit in
// their own collapsed block under the dated table, never in it, and the chart draws
// one only when its registered run ADMITTED it (verdict PASS and exploratory false),
// hollow, at the lv_dev offset. An exploratory row, or a row with no verdict, is
// listed and never drawn. Admission is to the gate's candidate list, never a claim.
const _PROG_SCREEN_PREFIX = "efv_v2_screen:";

function _progIsScreen(r) {
  return !!r && (String(r.model_id || "").indexOf(_PROG_SCREEN_PREFIX) === 0
    || (!!r.screening && typeof r.screening === "object"));
}

function _progScreenAdmitted(r) {
  return _progIsScreen(r) && r.verdict === "PASS"
    && !!r.screening && r.screening.exploratory === false;
}

function _progFrameLabel(prog, fid) {
  const f = (prog && prog.frames && prog.frames[fid]) || {};
  return f.label || fid;
}

function _progLatestHeadline(prog) {
  const head = prog && prog.headline_frame;
  const rows = _progRows(prog).filter(r => r.frame === head && r.role !== "tilted");
  return rows.length ? rows[rows.length - 1] : null;
}

// The latest row of a frame that is waiting to become the headline (EV-01 vm2).
function _progLatestCandidate(prog) {
  const rows = _progRows(prog).filter(r => r.role === "headline_candidate"
    && r.frame !== (prog && prog.headline_frame) && r.tilted !== true);
  return rows.length ? rows[rows.length - 1] : null;
}

function _progFmt(v, d) {
  return (v == null || isNaN(Number(v))) ? "-" : Number(v).toFixed(d);
}

function _progSigned(v, d) {
  if (v == null || isNaN(Number(v))) return "-";
  const n = Number(v);
  return (n > 0 ? "+" : "") + n.toFixed(d);
}

function _progCi(ci, d) {
  return (Array.isArray(ci) && ci.length === 2 && ci[0] != null && ci[1] != null)
    ? `${_progSigned(ci[0], d)} to ${_progSigned(ci[1], d)}` : "not recomputable";
}

// The served model a ledger row scored, in words (DS-02: eFV V2 serves from 2026-09-25).
function _progModelName(r) {
  const m = String((r && r.model_id) || "");
  return m === "efv_v2" ? "eFV V2 (served)" : m === "efv_v1" ? "eFV v1" : (m || "eFV");
}

function _methProgressLedger(prog, bt) {
  const row = _progLatestHeadline(prog);
  if (!row) return "";
  const rt = row.raters || {};
  const efv = (rt.efv || {}).spearman, cons = (rt.prospx_consensus || {}).spearman;
  const leg = _progConsLeg(row) || {};
  const ciTxt = Array.isArray(leg.ci95) ? `, 95% CI ${_progCi(leg.ci95, 3)}` : "";
  const carriedTxt = leg.mde95_status === "carried"
    ? `, carried from ${escapeHtml(String(leg.mde95_carried_from || "an earlier frame"))}` : "";
  const floorTxt = leg.mde95 != null
    ? `, noise floor ${_progFmt(leg.mde95, 3)}${leg.mde95_estimator ? " (" + escapeHtml(leg.mde95_estimator) + carriedTxt + ")" : ""}` : "";
  const stale = !!(bt && bt.generated_at && row.last_verified_at
    && String(row.last_verified_at) < String(bt.generated_at));
  const chip = stale
    ? ` <span class="sacc-chip-warn" title="the backtest was regenerated after this row was last verified">stale: backtest ${escapeHtml(String(bt.generated_at).slice(0, 10))} is newer</span>`
    : ` <span class="sacc-chip-ok">verified ${escapeHtml(String(row.last_verified_at || row.date || "").slice(0, 10))}</span>`;
  const resolvable = row.resolvable === true;
  const corrTxt = _progIsCorrection(prog, row)
    ? ` <span class="sacc-chip-warn" title="${escapeHtml(_progNoteText(prog, row))}">${escapeHtml(_progCorrectionName(row))}, not model progress</span>` : "";
  // A headline candidate (EV-01 vm2) prints on its own line, in the neutral
  // style: it is not the claim until the owner has seen it.
  const cand = _progLatestCandidate(prog);
  let candTxt = "";
  if (cand) {
    const crt = cand.raters || {}, cleg = _progConsLeg(cand) || {};
    candTxt = `<p class="meth-window"><strong>${escapeHtml(_progFrameLabel(prog, cand.frame))}, ${escapeHtml(cand.date || "")} <span class="sacc-chip-warn">${escapeHtml(String(cand.role || "").replace(/_/g, " "))}</span>:</strong> n ${Number(cand.n || 0).toLocaleString()}, ${escapeHtml(_progModelName(cand))} ${_progFmt((crt.efv || {}).spearman, 3)} against PROSPX consensus ${_progFmt((crt.prospx_consensus || {}).spearman, 3)}, delta ${_progSigned(cleg.delta, 4)}${Array.isArray(cleg.ci95) ? `, 95% CI ${_progCi(cleg.ci95, 3)}` : ""}: <span class="sacc-verdict-null">${escapeHtml(cand.verdict || "")}</span>.${_progIsCorrection(prog, cand) ? ` <span class="sacc-chip-warn">${escapeHtml(_progCorrectionName(cand))}, not model progress</span>` : ""} ${escapeHtml(_progNoteText(prog, cand))}</p>`;
  }
  return `<div class="meth-chart scx-progress-head">
    <div class="meth-chart-title">eFV progress ledger <span class="meth-sub">the dated record of eFV against PROSPX consensus and the industry</span></div>
    <p class="meth-window"><strong>Latest, ${escapeHtml(row.date || "")}:</strong> on the ${escapeHtml(_progFrameLabel(prog, row.frame).toLowerCase())} frame (n ${Number(row.n || 0).toLocaleString()}), ${escapeHtml(_progModelName(row))} ${_progFmt(efv, 3)} against PROSPX consensus ${_progFmt(cons, 3)}, delta ${_progSigned(leg.delta, 4)}${ciTxt}${floorTxt}: <span class="${resolvable ? "sacc-verdict-win" : "sacc-verdict-null"}">${escapeHtml(row.verdict || "")}</span>.${corrTxt}${chip}</p>
    ${candTxt}
  </div>`;
}

function _progDateLabel(iso) {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(iso || ""));
  if (!m) return String(iso || "");
  const mon = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][Number(m[2]) - 1] || m[2];
  return `${mon} ${Number(m[3])}`;
}

// Horizontal offset of a mark from its date, so rows that share a date do not
// overprint: a headline candidate sits right of the headline row, correction
// rows further right, development rows left (lv_dev further than vm_dev), and a
// rebuilt-V2 development row (one that names its statistic) left of those. An
// admitted screening candidate sits at the lv_dev offset itself.
function _progDx(prog, r) {
  const cand = r.role === "headline_candidate";
  if (_progIsCorrection(prog, r)) return cand ? 27 : 18;
  // the served V2 rows sit right of any same-date v1 row of the same frame
  if (r.model_id === "efv_v2") return cand ? 13 : 4;
  if (cand) return 9;
  if (r.role !== "development") return 0;
  const base = r.frame === "lv_dev" ? -18 : -9;
  if (_progIsScreen(r)) return base;
  return r.statistic ? base - 18 : base;
}

function _methProgressChart(prog) {
  const rows = _progSeriesRows(prog);
  if (!rows.length) return "";
  // A phone gets a narrower drawing rather than a shrunken wide one, so the
  // axis labels stay legible at 390px.
  const narrow = (window.innerWidth || 1024) < 600;
  const W = narrow ? 340 : 580, H = narrow ? 240 : 250, ML = narrow ? 46 : 52, MR = narrow ? 10 : 16, MT = 16, MB = 40;
  const iW = W - ML - MR, iH = H - MT - MB;
  const legs = rows.map(r => _progConsLeg(r));
  const last = _progLatestHeadline(prog);
  const floor = last && _progConsLeg(last) ? _progConsLeg(last).mde95 : null;
  const vals = [];
  legs.forEach(l => {
    vals.push(Number(l.delta));
    if (Array.isArray(l.ci95) && l.ci95[0] != null) vals.push(Number(l.ci95[0]), Number(l.ci95[1]));
  });
  if (floor != null) vals.push(Number(floor), -Number(floor));
  vals.push(0);
  let lo = Math.min(...vals), hi = Math.max(...vals);
  const pad = (hi - lo) * 0.12 || 0.01;
  lo -= pad; hi += pad;
  const ts = rows.map(r => Date.parse(String(r.date) + "T00:00:00Z"));
  const t0 = Math.min(...ts), t1 = Math.max(...ts);
  // An inner pad keeps the first and last marks off the axes; rows that share a
  // date sit apart by a fixed offset (_progDx), so the pad follows the widest one.
  const anyCorr = rows.some(r => _progIsCorrection(prog, r));
  const PX = Math.max(18, ...rows.map(r => Math.abs(_progDx(prog, r)) + 16));
  const sx = t => (t1 === t0 ? ML + iW / 2 : ML + PX + ((t - t0) / (t1 - t0)) * (iW - 2 * PX));
  const sy = v => MT + iH - ((v - lo) / (hi - lo)) * iH;
  // Round tick steps (1, 2 or 5 times a power of ten) so the axis reads in
  // plain hundredths rather than at arbitrary fractions of the range.
  const raw = (hi - lo) / 6, mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const yStep = [1, 2, 5, 10].map(k => k * mag).find(s => s >= raw) || raw;
  const dec = Math.max(0, -Math.floor(Math.log10(yStep)));
  const grid = [];
  for (let v = Math.ceil(lo / yStep) * yStep; v <= hi + yStep / 1000; v += yStep) {
    const y = sy(v).toFixed(1);
    grid.push(`<line x1="${ML}" y1="${y}" x2="${ML + iW}" y2="${y}" stroke="var(--border-light)" stroke-width="0.5" stroke-dasharray="2,3"/>`,
      `<text x="${ML - 6}" y="${y}" dy="3" text-anchor="end" font-size="9" fill="var(--text-tertiary)">${_progSigned(Math.abs(v) < yStep / 1000 ? 0 : v, dec)}</text>`);
  }
  const band = floor != null
    ? `<rect x="${ML}" y="${sy(Number(floor)).toFixed(1)}" width="${iW}" height="${(sy(-Number(floor)) - sy(Number(floor))).toFixed(1)}" fill="var(--text-tertiary)" fill-opacity="0.12"/>`
    : "";
  const zero = `<line x1="${ML}" y1="${sy(0).toFixed(1)}" x2="${ML + iW}" y2="${sy(0).toFixed(1)}" stroke="var(--text-secondary)" stroke-width="1" stroke-dasharray="4,3"/>`;
  const col = _raterMeta("xfv").color;
  const marks = rows.map((r, i) => {
    const cand = r.role === "headline_candidate";
    const dev = r.role === "development";
    const dx = _progDx(prog, r);
    const l = legs[i], x = sx(ts[i]) + dx, y = sy(Number(l.delta));
    const ci = Array.isArray(l.ci95) && l.ci95[0] != null
      ? `<line x1="${x.toFixed(1)}" y1="${sy(Number(l.ci95[0])).toFixed(1)}" x2="${x.toFixed(1)}" y2="${sy(Number(l.ci95[1])).toFixed(1)}" stroke="${col}" stroke-width="1.6"/>`
        + [l.ci95[0], l.ci95[1]].map(v => `<line x1="${(x - 4).toFixed(1)}" y1="${sy(Number(v)).toFixed(1)}" x2="${(x + 4).toFixed(1)}" y2="${sy(Number(v)).toFixed(1)}" stroke="${col}" stroke-width="1.6"/>`).join("")
      : "";
    const tip = `<title>${escapeHtml(r.date)}: ${escapeHtml(r.model_id || "")}, ${escapeHtml(_progFrameLabel(prog, r.frame))}, n ${r.n}${r.statistic ? `, ${escapeHtml(r.statistic)}` : ""}, delta ${_progSigned(l.delta, 4)}, CI ${escapeHtml(_progCi(l.ci95, 4))}, ${escapeHtml(r.verdict || "")}</title>`;
    let mark;
    if (_progIsCorrection(prog, r)) {
      // A scoring fix: an open triangle, whatever the frame.
      mark = `<path d="M ${x.toFixed(1)},${(y - 5.5).toFixed(1)} L ${(x + 5.5).toFixed(1)},${(y + 4.5).toFixed(1)} L ${(x - 5.5).toFixed(1)},${(y + 4.5).toFixed(1)} Z" fill="var(--bg-secondary)" stroke="${col}" stroke-width="2">${tip}</path>`;
    } else if (r.trigger === "look") {
      mark = `<path d="M ${x.toFixed(1)},${(y - 6).toFixed(1)} L ${(x + 6).toFixed(1)},${y.toFixed(1)} L ${x.toFixed(1)},${(y + 6).toFixed(1)} L ${(x - 6).toFixed(1)},${y.toFixed(1)} Z" fill="${col}" stroke="var(--bg-secondary)" stroke-width="1">${tip}</path>`;
    } else if (cand) {
      mark = `<path d="M ${(x - 4.5).toFixed(1)},${(y - 4.5).toFixed(1)} L ${(x + 4.5).toFixed(1)},${(y - 4.5).toFixed(1)} L ${(x + 4.5).toFixed(1)},${(y + 4.5).toFixed(1)} L ${(x - 4.5).toFixed(1)},${(y + 4.5).toFixed(1)} Z" fill="var(--bg-secondary)" stroke="${col}" stroke-width="2">${tip}</path>`;
    } else if (_progIsScreen(r)) {
      // An admitted screening candidate: hollow with a dashed ring, never a claim.
      mark = `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="4.5" fill="var(--bg-secondary)" stroke="${col}" stroke-width="2" stroke-dasharray="2,1.5">${tip}</circle>`;
    } else if (dev) {
      mark = `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="4.5" fill="var(--bg-secondary)" stroke="${col}" stroke-width="2">${tip}</circle>`;
    } else {
      mark = `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="4.5" fill="${col}" stroke="var(--bg-secondary)" stroke-width="1">${tip}</circle>`;
    }
    return ci + mark;
  }).join("");
  const uniq = [...new Set(ts)].sort((a, b) => a - b);
  // Date labels never collide: walk right to left from the newest date and
  // keep a label only when it clears the last one kept by a label's width.
  const kept = [];
  uniq.slice().reverse().forEach(t => {
    if (!kept.length || sx(kept[kept.length - 1]) - sx(t) >= 56) kept.push(t);
  });
  const ticks = kept.reverse().map(t =>
    `<text x="${sx(t).toFixed(1)}" y="${MT + iH + 16}" text-anchor="middle" font-size="10" fill="var(--text-secondary)" font-weight="600">${escapeHtml(_progDateLabel(new Date(t).toISOString()))}</text>`).join("");
  const hasDev = rows.some(r => r.role === "development" && !_progIsScreen(r));
  const hasScreen = rows.some(r => _progIsScreen(r));
  const candRow = rows.find(r => r.role === "headline_candidate");
  const hasLook = rows.some(r => r.trigger === "look");
  const hasCorr = anyCorr;
  const legend = [
    `<span class="meth-legend-key"><span class="meth-legend-swatch" style="background:${col};border-radius:50%;"></span>${escapeHtml(_progFrameLabel(prog, prog.headline_frame || "vm"))} frame (headline)</span>`,
    candRow ? `<span class="meth-legend-key"><span class="meth-legend-swatch" style="background:var(--bg-secondary);border:2px solid ${col};"></span>${escapeHtml(_progFrameLabel(prog, candRow.frame))} (headline candidate, not yet the claim)</span>` : "",
    hasDev ? `<span class="meth-legend-key"><span class="meth-legend-swatch" style="background:var(--bg-secondary);border:2px solid ${col};border-radius:50%;"></span>development frame, spent, not a claim</span>` : "",
    hasScreen ? `<span class="meth-legend-key"><svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true"><circle cx="6" cy="6" r="4.5" fill="var(--bg-secondary)" stroke="${col}" stroke-width="1.6" stroke-dasharray="2,1.5"/></svg>admitted candidate (development, not a claim)</span>` : "",
    rows.some(r => r.statistic && !_progIsScreen(r)) ? `<span class="meth-legend-key">a development row that names its statistic (the rebuilt V2) reads Spearman within side and vintage, the statistic registered for the reserved reads; its pooled reading sits in the table</span>` : "",
    hasLook ? `<span class="meth-legend-key"><span class="meth-legend-swatch" style="background:${col};transform:rotate(45deg);"></span>reserved-frame look</span>` : "",
    hasCorr ? `<span class="meth-legend-key"><svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true"><path d="M 6,1 L 11,10.5 L 1,10.5 Z" fill="var(--bg-secondary)" stroke="${col}" stroke-width="1.6"/></svg>correction or frame change: a fix to how eFV is scored, to the rows it is trained and scored on, or a move of the headline to another frame, not model progress</span>` : "",
    floor != null ? `<span class="meth-legend-key"><span class="meth-legend-swatch" style="background:var(--text-tertiary);opacity:.35;"></span>plus or minus the noise floor (${_progFmt(floor, 3)})</span>` : "",
  ].filter(Boolean).join("");
  return `<div class="meth-chart">
    <div class="meth-chart-title">eFV minus PROSPX consensus, over time <span class="meth-sub">Spearman ρ against realized WAR, identical rows; whiskers are the 95% CI where the row carries one</span></div>
    <svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="eFV minus PROSPX consensus Spearman, by ledger date, with confidence intervals and the noise floor band">
      ${band}${grid.join("")}${zero}
      <line x1="${ML}" y1="${MT + iH}" x2="${ML + iW}" y2="${MT + iH}" stroke="var(--text-secondary)" stroke-width="1"/>
      <line x1="${ML}" y1="${MT}" x2="${ML}" y2="${MT + iH}" stroke="var(--text-secondary)" stroke-width="1"/>
      ${marks}${ticks}
    </svg>
    <div class="meth-legend">${legend}</div>
    <p class="meth-note">A point above zero is eFV ordering realized WAR better than the consensus on the same players. Inside the shaded band the difference is smaller than this sample can resolve, so no point inside it is a lead or a deficit. Rows backfilled from the committed history carry no interval, because one cannot be recomputed from a committed number. Tilted frames are never plotted.${_progRows(prog).some(r => r.role === "superseded") ? ` Rows of a frame that has lost the headline, ${escapeHtml(_progFrameLabel(prog, "vm"))}, are marked superseded in the table below and are not plotted.` : ""}${hasCorr ? " An open triangle is the same model specification rescored after a correction (to the scoring code or to the rows) or read on the frame that now carries the headline, so the step it shows is not progress." : ""}</p>
  </div>`;
}

function _progRaterCell(r, name) {
  const x = (r.raters || {})[name];
  if (!x || (x.spearman == null && x.auc == null)) return `<td>-</td>`;
  return `<td>${_progFmt(x.spearman, 3)}${x.auc != null ? ` / ${_progFmt(x.auc, 3)}` : ""}</td>`;
}

// The eFV cell. A development row of a v2 candidate carries eFV v1 on the
// same rows as well; it prints under the candidate's own figures.
function _progEfvCell(r) {
  const v1 = (r.raters || {}).efv_v1;
  const base = _progRaterCell(r, "efv");
  if (!v1 || (v1.spearman == null && v1.auc == null)) return base;
  return base.replace(/<\/td>$/, `<br><span class="meth-sub">v1 ${_progFmt(v1.spearman, 3)}${v1.auc != null ? ` / ${_progFmt(v1.auc, 3)}` : ""}</span></td>`);
}

function _progRowHtml(prog, r) {
  const leg = _progConsLeg(r);
  const mv = r.model_version || {};
  const trigTxt = _progIsCorrection(prog, r)
    ? `<br><span class="sacc-chip-warn">${escapeHtml(_progCorrectionName(r))}</span>`
    : (r.trigger ? `<br><span class="meth-sub">${escapeHtml(r.trigger)}</span>` : "");
  const model = `${escapeHtml(r.model_id || "")}${mv.commit ? ` <span class="meth-sub">${escapeHtml(mv.commit)}</span>` : ""}${trigTxt}`;
  const chipCls = r.role === "headline" ? "sacc-chip-ok" : "sacc-chip-warn";
  const frame = `${escapeHtml(_progFrameLabel(prog, r.frame))}${r.frame_version ? ` <span class="meth-sub">${escapeHtml(r.frame_version)}</span>` : ""}<br><span class="${chipCls}">${escapeHtml(String(r.role || "").replace(/_/g, " "))}</span>${r.role_was ? `<br><span class="meth-sub" title="${escapeHtml(r.role_changed || "")}">written as ${escapeHtml(String(r.role_was).replace(/_/g, " "))}</span>` : ""}${r.statistic ? `<br><span class="meth-sub">${escapeHtml(r.statistic)}</span>` : ""}`;
  let deltaCell;
  if (r.share && r.share.efv_right_share != null) {
    const ci = Array.isArray(r.share.ci95) ? ` (CI ${_progFmt(r.share.ci95[0] * 100, 0)}% to ${_progFmt(r.share.ci95[1] * 100, 0)}%)` : "";
    deltaCell = `eFV closer on ${_progFmt(r.share.efv_right_share * 100, 1)}%${ci}`;
  } else if (leg) {
    deltaCell = `${_progSigned(leg.delta, 4)}<br><span class="meth-sub">${escapeHtml(_progCi(leg.ci95, 3))}</span>`;
    const sec = r.secondary && r.secondary.deltas && r.secondary.deltas.vs_prospx_consensus;
    if (sec && sec.delta != null) {
      deltaCell += `<br><span class="meth-sub">pooled ${_progSigned(sec.delta, 4)} (${escapeHtml(_progCi(sec.ci95, 3))})</span>`;
    }
  } else {
    deltaCell = "-";
  }
  const floorCell = leg && leg.mde95 != null ? _progFmt(leg.mde95, 4) : "-";
  // Only a headline or reserved-frame row can carry a win colour; a tilted or
  // secondary row prints its verdict in the neutral style, whatever it says.
  const claimable = r.role === "headline" || r.role === "reserved";
  const verdictCls = (claimable && r.resolvable === true) ? "sacc-verdict-win" : "sacc-verdict-null";
  return `<tr>
    <td>${escapeHtml(r.date || "")}</td><td>${model}</td><td>${frame}</td>
    <td>${r.n != null ? Number(r.n).toLocaleString() : "-"}</td>
    ${_progEfvCell(r)}${_progRaterCell(r, "prospx_consensus")}${_progRaterCell(r, "mlb_pipeline")}${_progRaterCell(r, "fangraphs")}
    <td>${deltaCell}</td><td>${floorCell}</td>
    <td><span class="${verdictCls}">${escapeHtml(r.verdict || "-")}</span></td>
    <td class="meth-sub">${escapeHtml(_progNoteText(prog, r))}</td>
  </tr>`;
}

function _methProgressTable(prog) {
  const rows = _progRows(prog);
  if (!rows.length) return "";
  const head = `<thead><tr><th>Date</th><th>Model</th><th>Frame</th><th>n</th><th>eFV ρ / AUC</th><th>Consensus</th><th>Pipeline</th><th>FanGraphs</th><th>Delta vs consensus (CI95)</th><th>Floor</th><th>Verdict</th><th>Note</th></tr></thead>`;
  const main = rows.filter(r => r.role !== "tilted" && r.tilted !== true && r.role !== "secondary" && !_progIsScreen(r)).slice().reverse();
  const tilted = rows.filter(r => r.role === "tilted" || r.tilted === true).slice().reverse();
  const secondary = rows.filter(r => r.role === "secondary" && r.tilted !== true).slice().reverse();
  const mainHtml = main.length
    ? `<div class="table-scroll-x"><table class="meth-table">${head}<tbody>${main.map(r => _progRowHtml(prog, r)).join("")}</tbody></table></div>` : "";
  const tiltedHtml = tilted.length
    ? `<details class="scx-progress-tilted"><summary>Tilted frames (not evidence of skill), ${tilted.length} row${tilted.length === 1 ? "" : "s"}</summary>
        <p class="meth-note">Each of these frames hands one grader an information edge, so a lead on one is timing and not skill. The note on each row is the artifact's own statement of which way it tilts.</p>
        <div class="table-scroll-x"><table class="meth-table">${head}<tbody>${tilted.map(r => _progRowHtml(prog, r)).join("")}</tbody></table></div>
      </details>` : "";
  const secondaryHtml = secondary.length
    ? `<details class="scx-progress-secondary"><summary>Secondary measures (not the headline), ${secondary.length} row${secondary.length === 1 ? "" : "s"}</summary>
        <p class="meth-note">Measured on a different population or read than the headline frame. Each row's note says which.</p>
        <div class="table-scroll-x"><table class="meth-table">${head}<tbody>${secondary.map(r => _progRowHtml(prog, r)).join("")}</tbody></table></div>
      </details>` : "";
  return `<div class="meth-chart">
    <div class="meth-table-title">Every ledger row, newest first</div>
    ${mainHtml}${tiltedHtml}${secondaryHtml}
    <p class="meth-note">Rows are appended when a frame's measured numbers change, and their numbers are never edited; a row's role moves only when its frame's role does (a superseded row says so). Each row names the artifact it was copied from. The Pipeline and FanGraphs columns print each grader's own figures on the row's players; whether a gap to eFV survives the correction for testing several sources is read in the per-source table above, and a CI clear of zero is not a win on its own.</p>
  </div>`;
}

// One screening row: the arm's own numbers, copied by efv_progress.py from
// the screening artifact; nothing here computes or rounds a claim.
function _progScreenRowHtml(r) {
  const parts = String(r.model_id || "").split(":");
  const sc = r.screening || {};
  const leg = ((r.deltas && r.deltas.vs_efv_v2_base) || {}).spearman || {};
  const mv = r.model_version || {};
  const folds = sc.admitted_folds != null
    ? `<br><span class="meth-sub">admitted in ${escapeHtml(String(sc.admitted_folds))} fold${Number(sc.admitted_folds) === 1 ? "" : "s"}</span>` : "";
  const delta = leg.delta != null
    ? `${_progSigned(leg.delta, 4)}<br><span class="meth-sub">CI95 ${escapeHtml(_progCi(leg.ci95, 3))}; lower bound ${_progSigned(leg.lb95, 4)}</span>` : "-";
  const twin = sc.twin_inside_floor === true ? "inside its floor"
    : sc.twin_inside_floor === false ? "outside its floor" : "-";
  const admitted = _progScreenAdmitted(r) ? `<br><span class="meth-sub">admitted to the candidate list</span>` : "";
  const expl = sc.exploratory === true ? `<br><span class="sacc-chip-warn">exploratory, no verdict formed</span>` : "";
  return `<tr>
    <td>${escapeHtml(r.date || "")}</td>
    <td>${escapeHtml(parts[2] || r.model_id || "-")}${sc.wave != null ? ` <span class="meth-sub">wave ${escapeHtml(String(sc.wave))}</span>` : ""}</td>
    <td>${escapeHtml(parts[3] || "-")}</td>
    <td>${escapeHtml(sc.head ? String(sc.head) : "coverage, no head")}${folds}</td>
    <td>${delta}</td><td>${_progFmt(leg.floor, 4)}</td><td>${_progFmt(leg.holm_p, 3)}</td>
    <td>${twin}</td>
    <td><span class="sacc-verdict-null">${escapeHtml(r.verdict || "-")}</span>${admitted}${expl}</td>
    <td class="meth-sub">${escapeHtml(mv.label || "-")}</td>
  </tr>`;
}

// The screening lab's collapsed block (EFV3 lane B s5, owner default E3-Q23): every
// screening row the ledger holds, newest first, and the families no source can be
// screened on yet. It reads only rows already on the ledger.
function _progScreenBlock(prog) {
  const rows = _progRows(prog).filter(r => _progIsScreen(r)).slice().reverse();
  const n = rows.length;
  const head = `<thead><tr><th>Date</th><th>Candidate</th><th>Side</th><th>Head</th><th>Within delta vs V2 base (CI95; lower bound)</th><th>Floor</th><th>Holm p</th><th>Twin</th><th>Verdict</th><th>Label</th></tr></thead>`;
  const table = n
    ? `<div class="table-scroll-x"><table class="meth-table">${head}<tbody>${rows.map(r => _progScreenRowHtml(r)).join("")}</tbody></table></div>`
    : `<p class="meth-note">No screening row is on the ledger yet.</p>`;
  const noSource = [
    ["IL stints", "the injury history starts in 2017 and is thin before 2026; first read once the resolved cohort holds a hundred stints recorded before each list date"],
    ["Signing bonus before the 2017 draft classes", "no table holds it; never, unless a pre-2017 bonus table is ingested"],
    ["College production", "the college tables start with the 2021 and 2022 classes; a count-only StatsAPI probe of earlier seasons decides, otherwise the 2021 class first resolves about 2029"],
    ["AAA and Florida State League Statcast, A-ball signals", "tracking starts in 2021 (FSL) and 2023 (AAA); the 2022 list first resolves in 2027 and the 2024 list in 2029; the chain's second link can be screened now"],
    ["Modern pitch-level data and pitch rates", "2023 onward, pitch rates 2026 only; the same dates as the Statcast line"],
    ["Tracked physical data (bat speed, bat tracking, sprint and arm)", "2027 and later"],
    ["eBR", "not built; first read after the eBR plan's integration task"],
    ["BA, ESPN, Just Baseball and TJStats report text", "archives start between 2023 and 2026; never on the reserved list vintages; the 2023 list first resolves in 2027"],
  ];
  return `<div class="meth-chart"><details class="scx-progress-screening"><summary>Screening lab (development; admits candidates to the registered list, proves nothing), ${n} row${n === 1 ? "" : "s"}</summary>
      <p class="meth-note">A screening row measures one candidate column, offered to one head of the eFV V2 assembly, against the same assembly without it, on development list vintages that have already been read. PASS means the column met every pre-registered admission clause, and admission means only that the column joins the V2 gate's registered candidate list. It does not mean eFV got better and it is not an accuracy claim: a candidate reaches the served grade only through that registered list and the reserved read. Every other verdict is a null or a recorded absence, kept with its numbers; an exploratory row forms no verdict. The chart above draws only admitted candidates, hollow.</p>
      ${table}
      <p class="meth-note">Families with no vintage-matched source are recorded and never screened. The first possible read of each:</p>
      <ul class="meth-refs">${noSource.map(([k, v]) => `<li><strong>${escapeHtml(k)}</strong>: ${escapeHtml(v)}</li>`).join("")}</ul>
    </details></div>`;
}

function _methProgressSection(bt) {
  const prog = _S.progress;
  if (!prog || prog.__error || !_progRows(prog).length) return "";
  return `<h2 class="meth-h">Is eFV pulling ahead? The progress ledger</h2>
    ${_methProgressLedger(prog, bt)}
    ${_methProgressChart(prog)}
    ${_methProgressTable(prog)}
    ${_progScreenBlock(prog)}`;
}

// ---- eFV scoreboard matrix (EFV3_D4; EFV3_PLAN.md section 6, LANE_D.md 3.4 and 3.8)
// The owner asked to see eFV against consensus and the industry in as many
// specific categories as possible. The matrix artifact (tools/efv_matrix.py)
// scores every category cell on every frame it may read; this section prints
// it and computes nothing: every count, interval, floor and reading word is the
// artifact's own. Colour attaches only to AHEAD and BEHIND, which a cell earns
// only by surviving its frame's family; every other reading is neutral, an
// unpowered cell is hatched, a development frame carries its chip. No word from
// a stratum cell reaches the hero, the share card, the eFV verdict or any
// methodology sentence. Same lazy idiom as _loadProgress; an absent artifact
// drops the section and never the view.
function _loadMatrix() {
  if (_S.matrix || _S.matrixLoading) return;
  _S.matrixLoading = true;
  const rerender = () => { if (_S.view === "source-comparison") renderSourceComparison(); };
  fetch("/data/efv_matrix_eval.json", { cache: "no-cache" })
    .then(r => (r.ok ? r.json() : null))
    .then(j => { _S.matrix = j || { __error: true }; rerender(); })
    .catch(() => { _S.matrix = { __error: true }; rerender(); });
}

const _MX_DIM_LABELS = { overall: "Overall", side: "Side", position_family: "Position family",
  level_at_list: "Level at list", age_band: "Age at list", list_year: "List year",
  archetype: "Acquisition and side", source_disagreement: "Source disagreement" };

function _mxN(v) { return (v == null || isNaN(Number(v))) ? "-" : Number(v).toLocaleString("en-US"); }

function _mxUi() {
  if (!_S.mxUi) _S.mxUi = { frame: null, stat: null, comp: null, dim: null, l6: null };
  return _S.mxUi;
}

// Frames the grid can show: the ones the artifact scored (reserved frames
// print their line and their pre-registered cells, never a grid).
function _mxGridFrames(mx) {
  const fr = (mx && mx.frames) || {};
  return Object.keys(fr).filter(k => !fr[k].reserved && fr[k].cells && Object.keys(fr[k].cells).length);
}

// "vintage-matched, timing-pinned frame", in the producer's own words where its
// line carries them, else the ledger's frame label.
function _mxFrameLabel(prog, mx, fid) {
  const fr = ((mx && mx.frames) || {})[fid] || {};
  const m = /^On the (.+?) \(n /.exec(String((fr.summary || {}).line || ""));
  if (m) return m[1];
  const pl = prog && !prog.__error && prog.frames && prog.frames[fid] && prog.frames[fid].label;
  return pl ? `${String(pl).toLowerCase()} frame` : String(fid);
}

function _mxChipLabel(prog, mx, fid) {
  const pl = prog && !prog.__error && prog.frames && prog.frames[fid] && prog.frames[fid].label;
  if (pl) return String(pl);
  const s = _mxFrameLabel(prog, mx, fid);
  return s.charAt(0).toUpperCase() + s.slice(1);
}

function _mxDimLabel(mx, dim) {
  const base = _MX_DIM_LABELS[dim] || String(dim).replace(/_/g, " ");
  const side = ((mx.design || {}).dimension_side || {})[dim];
  const disclosed = ((mx.design || {}).disclosed_dimensions || []).includes(dim);
  return base + (side === "hit" ? " (hitters only)" : side === "pit" ? " (pitchers only)" : "")
    + (disclosed ? " (grade-derived)" : "");
}

function _mxCellLabel(dim, key) {
  const k = String(key);
  if (dim === "overall") return "Every row";
  if (dim === "side") return k === "hit" ? "Hitters" : k === "pit" ? "Pitchers" : k;
  if (k === "unknown") return "Unknown";
  if (dim === "archetype") {
    const m = /^unknown_(bat|arm)$/.exec(k);
    if (m) return m[1] === "bat" ? "Acquisition unknown, bats" : "Acquisition unknown, arms";
    return _saccLabel(k);
  }
  if (dim === "age_band" || dim === "position_family") return _saccLabel(k);
  if (dim === "level_at_list") return k === "none" ? "No level at list" : k;
  if (dim === "source_disagreement") return `FanGraphs minus Pipeline, ${k.replace(/_/g, " ")}`;
  return k;
}

// The statistic tabs, in the artifact's order; the two six-season cuts share one tab.
function _mxStatTabs(fr) {
  const out = [];
  (Array.isArray(fr.statistics) ? fr.statistics : []).forEach(k => {
    const tab = String(k).indexOf("spearman_l6_") === 0 ? "spearman_l6" : k;
    if (!out.includes(tab)) out.push(tab);
  });
  return out;
}

function _mxL6Keys(fr) {
  return (Array.isArray(fr.statistics) ? fr.statistics : []).filter(k => String(k).indexOf("spearman_l6_") === 0);
}

function _mxStatKey(fr, tab) {
  if (tab !== "spearman_l6") return tab;
  const keys = _mxL6Keys(fr);
  const ui = _mxUi();
  return keys.includes(ui.l6) ? ui.l6 : keys[0];
}

function _mxStatTabLabel(mx, fr, tab) {
  if (tab === "spearman_within") return "Within Spearman";
  if (tab === "spearman_pooled") return "Pooled Spearman";
  if (tab === "spearman_l6") return "Six-season label";
  if (tab === "mae") return "MAE";
  const desc = String(((mx.design || {}).statistics || {})[tab] || "");
  let m = /at (?:career WAR|W3) >= ([\w.]+)/.exec(desc);
  if (m) {
    const thr = m[1] === "w_star_dev" ? `w* ${_progFmt((fr.w_star_dev || {}).w_star, 2)}` : m[1];
    return `AUC at ${thr}${fr.veto_leg === tab ? " (veto leg)" : ""}`;
  }
  m = /on (\w+) \(/.exec(desc);
  if (m) return `AUC on ${m[1]}${fr.veto_leg === tab ? " (veto leg)" : ""}`;
  return String(tab);
}

// Colour attaches to AHEAD and BEHIND only, and never on a development frame.
function _mxReadingClass(reading, dev) {
  if (!dev && reading === "AHEAD") return "sacc-verdict-win";
  if (!dev && reading === "BEHIND") return "sacc-verdict-loss";
  return "sacc-verdict-null";
}

// One frame's line, from its summary block: the claim frame prints its family
// counts, a development frame prints what the family would read with its chip,
// a frame with no family prints the producer's own line, and a reserved frame
// prints its pre-registered cell count and nothing else.
function _mxFrameLine(prog, mx, fid) {
  const fr = mx.frames[fid] || {}, sm = fr.summary || {}, pr = (mx.design || {}).printed || {};
  const label = _mxFrameLabel(prog, mx, fid);
  if (fr.reserved) {
    const pc = fr.pre_registered_cells || {};
    const nCells = Object.values(pc).reduce((t, v) => t + (Array.isArray(v) ? v.length : 0), 0);
    const cap = label.charAt(0).toUpperCase() + label.slice(1);
    return `<li><strong>${escapeHtml(cap)}</strong>: <span class="sacc-chip-warn">${escapeHtml(pr.RESERVED_PENDING || "")}</span> ${_mxN(nCells)} cells on ${_mxN(Object.keys(pc).length)} dimensions are registered and read once, by the look runner.</li>`;
  }
  const k = sm.k_family_s;
  if (!k) return `<li>${escapeHtml(sm.line || "")}</li>`;
  const dev = fr.development === true;
  const c = (dev ? sm.would_read_on_a_claim_frame : sm.counts) || {};
  const parts = [`${_mxN(c.ahead)} cells ahead`, `${_mxN(c.behind)} behind`,
    `${_mxN(c.equivalent)} equivalent`, `${_mxN(c.unresolved)} not resolvable`];
  if (Number(c.flagged_uncorrected)) parts.push(`${_mxN(c.flagged_uncorrected)} clearing their own floor but not the family`);
  parts.push(`${_mxN(c.unpowered)} unpowered of ${_mxN(k)}`);
  const tail = `at alpha ${escapeHtml(String(sm.alpha))} the family would flag ${escapeHtml(String(sm.expected_false_flags_by_construction))} cells by chance`;
  const head = `On the ${escapeHtml(label)} (n ${_mxN(fr.n)})`;
  const under = Number(sm.under_floor)
    ? ` <span class="meth-sub">${_mxN(sm.under_floor)} more cells sit under the floor, outside the family.</span>` : "";
  if (dev) {
    return `<li>${head}: <span class="sacc-chip-warn">${escapeHtml(pr.DEVELOPMENT || "")}</span>; read as a claim frame, ${parts.join(", ")}; ${tail}.${under}</li>`;
  }
  return `<li>${head}: ${parts.join(", ")}; ${tail}.${under}</li>`;
}

// The reading of one cell on the chosen statistic and comparator. The cell's
// primary statistic against a family comparator carries the family's word; every
// other leg carries its own uncorrected word.
function _mxReadingHtml(mx, fr, cell, cmp, statKey, st) {
  const pr = (mx.design || {}).printed || {};
  const dev = fr.development === true;
  const devChip = dev ? ` <span class="sacc-chip-warn">${escapeHtml(pr.DEVELOPMENT || "")}</span>` : "";
  if (!cmp || cmp.reading === "NOT_SCORED" || !Number(cmp.n)) {
    return `<span class="sacc-verdict-null">${escapeHtml(pr.NOT_SCORED || "")}</span>`;
  }
  if (cell.scored === false || !st) {
    const r = cmp.reading || "NOT_SCORED";
    return `<span class="${_mxReadingClass(r, dev)}">${escapeHtml(cmp.printed || pr[r] || r)}</span>${cell.note ? `<span class="meth-sub mx-note">${escapeHtml(cell.note)}</span>` : ""}`;
  }
  if (st.reading == null) {
    return `<span class="sacc-verdict-null">${escapeHtml(st.role || st.status || "")}</span>`;
  }
  const inFamily = !!(cmp.family && cmp.primary && cmp.primary.leg === statKey);
  let r = st.reading;
  if (inFamily) r = dev ? (cmp.reading_if_claim_frame || st.reading) : (cmp.reading || st.reading);
  let word = pr[r] || r;
  // Why a scored leg is unpowered, from its own numbers and the design floors.
  if (r === "UNPOWERED") {
    const d = mx.design || {};
    word += Number(st.n) < Number(d.floor_rows) ? ` (n ${_mxN(st.n)})`
      : (st.n_pos != null && Math.min(Number(st.n_pos), Number(st.n_neg)) < Number(d.auc_min_positives)) ? ` (${_mxN(Math.min(Number(st.n_pos), Number(st.n_neg)))} in the smaller class)`
      : ` (floor wider than ${escapeHtml(String(d.unpowered_mde95))})`;
  }
  let side = "";
  if (r === "FLAGGED_UNCORRECTED") {
    side = inFamily && cmp.k != null
      ? ` <span class="meth-sub">k ${_mxN(cmp.k)}, ${escapeHtml(String(cmp.expected_false_flags_by_construction))} expected by chance</span>`
      : ` <span class="meth-sub">uncorrected, in no family</span>`;
  }
  const note = inFamily
    ? `<span class="meth-sub mx-note">family ${escapeHtml(String(cmp.family))}${cmp.k != null ? `, k ${_mxN(cmp.k)}` : ""}</span>`
    : `<span class="meth-sub mx-note">${escapeHtml(st.note || "")}</span>`;
  return `<span class="${_mxReadingClass(r, dev)}">${escapeHtml(word)}</span>${side}${devChip}${note}`;
}

// Delta, its 95% interval and the equivalence band, on the column's one scale.
function _mxWhisker(st, ext, margin) {
  const pos = v => 50 + 50 * Math.max(-1, Math.min(1, Number(v) / ext));
  const band = margin != null
    ? `<span class="mx-band" style="left:${pos(-margin).toFixed(2)}%;width:${(pos(margin) - pos(-margin)).toFixed(2)}%;"></span>` : "";
  const zero = `<span class="mx-zero" style="left:${pos(0).toFixed(2)}%;"></span>`;
  if (!st || st.delta == null || isNaN(Number(st.delta))) return `<div class="mx-whisk">${band}${zero}</div>`;
  const ci = Array.isArray(st.ci95) && st.ci95[0] != null && st.ci95[1] != null
    ? `<span class="mx-ci" style="left:${pos(st.ci95[0]).toFixed(2)}%;width:${(pos(st.ci95[1]) - pos(st.ci95[0])).toFixed(2)}%;"></span>` : "";
  const tip = `eFV minus the comparator ${_progSigned(st.delta, 4)}, 95% CI ${_progCi(st.ci95, 4)}, bootstrap SD ${_progFmt(st.sd, 4)}, floor ${_progFmt(st.mde95, 4)}`;
  return `<div class="mx-whisk" title="${escapeHtml(tip)}">${band}${zero}${ci}<span class="mx-dot" style="left:${pos(st.delta).toFixed(2)}%;"></span></div>`;
}

// Round tick steps (1, 2 or 5 times a power of ten) across the symmetric scale.
function _mxAxis(ext, digits) {
  const raw = ext / 2, mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const step = [1, 2, 5, 10].map(k => k * mag).find(s => s >= raw) || raw;
  const dec = Math.max(digits, -Math.floor(Math.log10(step)));
  const out = [];
  for (let v = -Math.floor(ext / step) * step; v <= ext + step / 1000; v += step) {
    const at = 50 + 50 * (v / ext);
    out.push(`<span style="left:${at.toFixed(2)}%;">${_progSigned(Math.abs(v) < step / 1000 ? 0 : v, dec)}</span>`);
  }
  return `<div class="mx-axis" aria-hidden="true">${out.join("")}</div>`;
}

function _mxGrid(mx, fr, tab, comp) {
  const d = mx.design || {};
  const statKey = _mxStatKey(fr, tab);
  const isAuc = String(statKey).indexOf("auc_") === 0;
  const isMae = statKey === "mae";
  const margin = isMae ? null : d.equivalence_margin;
  const dims = ["overall"].concat((d.dimensions || []).filter(x => x !== "overall"));
  const ui = _mxUi();
  const pick = dims.filter(x => x !== "overall" && fr.cells[x]);
  const cur = pick.includes(ui.dim) ? ui.dim : pick[0];
  const rows = [];
  dims.forEach(dim => Object.entries(fr.cells[dim] || {}).forEach(([key, cell]) => {
    const cmp = (cell.comparators || {})[comp];
    const st = cmp && cmp.statistics ? cmp.statistics[statKey] : null;
    rows.push({ dim, key, cell, cmp, st });
  }));
  const vals = [];
  rows.forEach(r => {
    if (!r.st || r.st.delta == null) return;
    vals.push(Math.abs(Number(r.st.delta)));
    if (Array.isArray(r.st.ci95)) r.st.ci95.forEach(v => { if (v != null) vals.push(Math.abs(Number(v))); });
  });
  if (margin != null) vals.push(Number(margin));
  const ext = (Math.max(...vals.filter(v => !isNaN(v)), 0) || Number(d.equivalence_margin) || 1) * 11 / 10;
  const digits = isMae ? 1 : 2;
  const head = `<div class="mx-row mx-head" role="row"><div class="mx-c-cell" role="columnheader">Cell</div><div class="mx-c-n" role="columnheader">n (hit / pit)</div>${isAuc ? `<div class="mx-c-pos" role="columnheader">Positives</div>` : ""}<div class="mx-c-delta" role="columnheader">eFV minus ${escapeHtml(((d.comparators || {})[comp]) || comp)}, 95% CI${_mxAxis(ext, digits)}</div><div class="mx-c-mde" role="columnheader">Floor (mde95)</div><div class="mx-c-read" role="columnheader">Reading</div></div>`;
  const body = dims.filter(dim => fr.cells[dim]).map(dim => {
    const off = dim !== "overall" && dim !== cur ? " mx-dim-off" : "";
    const lines = rows.filter(r => r.dim === dim).map(r => {
      const c = r.cell, st = r.st, cmp = r.cmp || {};
      const unp = (st && (st.reading === "UNPOWERED" || (st.reading == null && cmp.reading === "UNPOWERED")))
        || (!st && cmp.reading === "UNPOWERED");
      const nTxt = st && st.n != null ? st.n : (cmp.n != null ? cmp.n : c.n);
      const sub = Number(nTxt) === Number(c.n)
        ? `${_mxN(c.n_hit)} hit / ${_mxN(c.n_pit)} pit` : `of ${_mxN(c.n)} in the cell`;
      const dText = st && st.delta != null
        ? `<div class="mx-dtext">${_progSigned(st.delta, isMae ? 3 : 4)} <span class="meth-sub">${escapeHtml(_progCi(st.ci95, 3))}</span></div>`
        : `<div class="mx-dtext meth-sub">${escapeHtml(st && st.status ? st.status : "no interval")}</div>`;
      return `<div class="mx-row${unp ? " mx-row-unpowered" : ""}" role="row">
        <div class="mx-c-cell" role="cell">${escapeHtml(_mxCellLabel(r.dim, r.key))}</div>
        <div class="mx-c-n" role="cell">${_mxN(nTxt)}<span class="meth-sub mx-note">${sub}</span></div>
        ${isAuc ? `<div class="mx-c-pos" role="cell">${st && st.n_pos != null ? _mxN(st.n_pos) : "-"}</div>` : ""}
        <div class="mx-c-delta" role="cell">${_mxWhisker(st, ext, margin)}${dText}</div>
        <div class="mx-c-mde" role="cell">${st ? _progFmt(st.mde95, 4) : "-"}</div>
        <div class="mx-c-read" role="cell">${_mxReadingHtml(mx, fr, c, r.cmp, statKey, st)}</div>
      </div>`;
    }).join("");
    return `<div class="mx-dim${off}" role="rowgroup" data-mx-dim="${escapeHtml(dim)}"><div class="mx-dimhead">${escapeHtml(_mxDimLabel(mx, dim))}</div>${lines}</div>`;
  }).join("");
  const select = pick.length
    ? `<label class="mx-dim-pick"><span class="gl-microlabel">Category</span><select class="eephus-select" data-mx-select="dim" aria-label="Category shown">${pick.map(x => `<option value="${escapeHtml(x)}"${x === cur ? " selected" : ""}>${escapeHtml(_mxDimLabel(mx, x))}</option>`).join("")}</select></label>` : "";
  const desc = String((d.statistics || {})[statKey] || "");
  return `${select}<div class="mx-grid${isAuc ? " mx-auc" : ""}" role="table" aria-label="eFV minus the comparator by category cell">${head}${body}</div>
    <p class="meth-note">${escapeHtml(desc.charAt(0).toUpperCase() + desc.slice(1))}.${isMae ? " MAE is in WAR: a negative difference is eFV missing by less, and the equivalence band is not drawn because the margin is a rank-statistic margin." : ""}</p>`;
}

function _mxLegend(mx, fr) {
  const d = mx.design || {}, pr = d.printed || {};
  const S = (fr.families || {}).S || {};
  const hs = (fr.holm || {}).S || {};
  const comps = d.comparators || {};
  const fam = S.k
    ? `The family: ${_mxN(S.k)} stratum cells at or above the floor of ${_mxN(S.floor_rows)} rows, eFV against ${escapeHtml(comps[S.comparator] || S.comparator || "")} on each cell's primary statistic, ${escapeHtml(hs.procedure || "Holm step-down, one-sided")}, at alpha ${escapeHtml(String(S.alpha))}; ${escapeHtml(String(S.expected_false_flags_by_construction))} cells would clear by chance alone.`
    : `${escapeHtml(S.note || "")}.`;
  const disclosed = (d.disclosed_dimensions || []).map(x => _MX_DIM_LABELS[x] || x).join(", ");
  const banned = (d.banned_dimensions || []).join(", ");
  const items = [
    `<span class="meth-legend-key"><span class="meth-legend-swatch" style="background:var(--text-tertiary);opacity:.3;"></span>the registered equivalence margin (plus or minus ${escapeHtml(String(d.equivalence_margin))})</span>`,
    `<span class="meth-legend-key"><svg width="26" height="10" viewBox="0 0 26 10" aria-hidden="true"><line x1="1" y1="5" x2="25" y2="5" stroke="var(--text-secondary)" stroke-width="2"/><circle cx="13" cy="5" r="4" fill="var(--text-primary)"/></svg>eFV minus the comparator, with its 95% interval</span>`,
    `<span class="meth-legend-key"><span class="meth-legend-swatch mx-hatch-swatch"></span>${escapeHtml(pr.UNPOWERED || "")}</span>`,
  ].join("");
  return `<div class="meth-legend">${items}</div>
    <ul class="mx-lines mx-legend-notes">
      <li>${fam} Only a cell that survives the family can read "${escapeHtml(pr.AHEAD || "")}" or "${escapeHtml(pr.BEHIND || "")}", and only those two carry colour.</li>
      <li>The AUC legs, the six-season label, MAE and every industry comparator on a stratum cell sit in no family: each prints an uncorrected interval, not a claim. "${escapeHtml(pr.FLAGGED_UNCORRECTED || "")}" is drawn neutral with the family's k beside it.</li>
      <li>Ties are ties: "${escapeHtml(pr.EQUIVALENT || "")}" means the whole interval sits inside the registered equivalence margin; "${escapeHtml(pr.UNRESOLVED || "")}" means it does not, and the cell resolves nothing. They are different readings and neither is a lead.</li>
      <li>"${escapeHtml(pr.UNPOWERED || "")}" is hatched: under ${_mxN(d.floor_rows)} rows, under ${_mxN(d.auc_min_positives)} positives on an AUC tab, or a floor wider than ${escapeHtml(String(d.unpowered_mde95))}. A development frame carries the chip "${escapeHtml(pr.DEVELOPMENT || "")}"; a reserved frame reads "${escapeHtml(pr.RESERVED_PENDING || "")}".</li>
      ${disclosed ? `<li>${escapeHtml(disclosed)} is the one grade-derived dimension: the gap between two sources' grades, never a grade level.</li>` : ""}
      <li>No dimension is keyed on an FV level: a realized-WAR read by FV cell waits for the one registered look in docs/PROSPECT_ANCHOR_GATE.md.${banned ? ` Never a dimension: ${escapeHtml(banned)}.` : ""}</li>
    </ul>`;
}

function _mxInner(prog, mx) {
  const ui = _mxUi();
  const frames = _mxGridFrames(mx);
  const fid = frames.includes(ui.frame) ? ui.frame : frames[0];
  const lines = Object.keys(mx.frames || {}).map(k => _mxFrameLine(prog, mx, k)).join("");
  const lb = mx.label || {}, code = mx.code || {};
  const stamp = `<p class="meth-window"><strong>Run of ${escapeHtml(String(mx.generated_at || "").slice(0, 10))}:</strong> label ${escapeHtml(String(lb.id || lb.provider || ""))}, resolved through ${escapeHtml(String(lb.resolved_through))}${code.commit ? ` <span class="meth-sub">code ${escapeHtml(String(code.commit).slice(0, 8))}</span>` : ""}. ${escapeHtml(lb.epoch ? lb.epoch.charAt(0).toUpperCase() + lb.epoch.slice(1) + "." : "")} ${escapeHtml(mx.role ? mx.role.charAt(0).toUpperCase() + mx.role.slice(1) + "." : "")}</p>`;
  if (!fid) return `${stamp}<ul class="mx-lines">${lines}</ul>`;
  const fr = mx.frames[fid];
  const tabs = _mxStatTabs(fr);
  const tab = tabs.includes(ui.stat) ? ui.stat : tabs[0];
  const comps = (Array.isArray(fr.comparators) ? fr.comparators : []);
  const comp = comps.includes(ui.comp) ? ui.comp : (mx.design || {}).claim_comparator || comps[0];
  const chip = (k, v, lbl, on) => `<button class="chip${on ? " active" : ""}" type="button" data-mx-k="${k}" data-mx-v="${escapeHtml(v)}">${escapeHtml(lbl)}</button>`;
  const frameBar = `<div class="filter-bar mx-bar"><span class="gl-microlabel">Frame</span>${frames.map(f => chip("frame", f, _mxChipLabel(prog, mx, f), f === fid)).join("")}</div>`;
  const statBar = `<div class="filter-bar mx-bar"><span class="gl-microlabel">Statistic</span>${tabs.map(t => chip("stat", t, _mxStatTabLabel(mx, fr, t), t === tab)).join("")}</div>`;
  const l6 = tab === "spearman_l6" ? `<div class="filter-bar mx-bar"><span class="gl-microlabel">Rows</span>${_mxL6Keys(fr).map(k => {
    const m = /six-season label, (.+)$/.exec(String(((mx.design || {}).statistics || {})[k] || ""));
    return chip("l6", k, m ? m[1] : k, k === _mxStatKey(fr, tab));
  }).join("")}</div>` : "";
  const compBar = `<div class="filter-bar mx-bar"><span class="gl-microlabel">Against</span>${comps.map(c => chip("comp", c, ((mx.design || {}).comparators || {})[c] || c, c === comp)).join("")}</div>`;
  const overall = ((fr.cells.overall || {}).all || {});
  const oc = (overall.comparators || {})[comp];
  const grid = (!oc || oc.reading === "NOT_SCORED" || !Number(oc.n))
    ? `<p class="meth-note"><strong>${escapeHtml(((mx.design || {}).comparators || {})[comp] || comp)}:</strong> ${escapeHtml(((mx.design || {}).printed || {}).NOT_SCORED || "")} on this frame.</p>`
    : _mxGrid(mx, fr, tab, comp);
  return `${stamp}<ul class="mx-lines">${lines}</ul>
    <div class="meth-chart">${frameBar}${statBar}${l6}${compBar}${grid}${_mxLegend(mx, fr)}</div>`;
}

function _mxBind() {
  const root = document.getElementById("scx-matrix");
  if (!root) return;
  const redraw = () => { const b = root.querySelector(".scx-matrix-body"); if (b) b.innerHTML = _mxInner(_S.progress, _S.matrix); };
  root.onclick = e => {
    const b = e.target.closest("[data-mx-k]");
    if (!b) return;
    _mxUi()[b.dataset.mxK] = b.dataset.mxV;
    redraw();
  };
  root.onchange = e => {
    const s = e.target.closest("[data-mx-select]");
    if (!s) return;
    _mxUi()[s.dataset.mxSelect] = s.value;
    redraw();
  };
}

function _methMatrixSection(prog, mx) {
  if (!mx || mx.__error || !mx.frames || !mx.design) return "";
  return `<div class="scx-matrix" id="scx-matrix">
    <h2 class="meth-h" id="efv-matrix">Category by category: the eFV scoreboard matrix</h2>
    <p class="meth-note">Each row is one category of prospect, scored on the same rows for eFV and the comparator: the difference in the chosen statistic with its 95% interval, the smallest difference that category's rows could resolve, and the reading the artifact gives it. The headline above is the claim; a category reading never changes it.</p>
    <div class="scx-matrix-body">${_mxInner(prog, mx)}</div>
  </div>`;
}

// ---- Label pool panel (EFV3_A8; EFV3_PLAN.md sections 3 and 6) --------------
// The rows the eFV program can be trained and read on, from the label pool
// census: rows per frame with the outcome-blind identity route, the floor each
// frame size could resolve, which label views resolve this year and next, and
// the census stamp (WAR provider, resolved_through). Counts and floors only:
// no grade is scored here, no rho, AUC or delta prints, nothing is grouped by
// a consensus FV level, and the reserved frames show their published counts
// and nothing else. Same lazy idiom as _loadProgress; an absent artifact drops
// the panel and never the view.
function _loadLabelPool() {
  if (_S.labelPool || _S.labelPoolLoading) return;
  _S.labelPoolLoading = true;
  const rerender = () => { if (_S.view === "source-comparison") renderSourceComparison(); };
  fetch("/data/efv_label_pool_census.json", { cache: "no-cache" })
    .then(r => (r.ok ? r.json() : null))
    .then(j => { _S.labelPool = j || { __error: true }; rerender(); })
    .catch(() => { _S.labelPool = { __error: true }; rerender(); });
}

// source_backtest.MIN_LAG_YEARS (test-pinned): a debut cohort enters the
// vintage-matched frame once this many seasons separate it from the census year.
const _LP_VM_MIN_LAG = 3;
const _LP_PROVIDERS = { ewar_v2: "eWAR v2", ewar_merged: "eWAR merged", bwar: "Baseball-Reference WAR", fwar: "FanGraphs WAR" };
const _LP_ROUTES = [["name_unique", "name, unique"], ["name_side", "side tiebreak"],
  ["name_recency", "recency tiebreak"], ["ambiguous", "ambiguous"], ["no_candidate", "no candidate"], ["other", "other"]];
const _LP_RESOLVED = ["name_unique", "name_side", "name_recency"];
// Row counts the plan names (LANE_A.md section 2); a count the census does not
// list prints without a caption.
const _LP_N_CAPTIONS = { 149: "R-VM look 1, both scored sources", 176: "R-VM look 1, consensus present",
  210: "R-VM look 1 as first registered", 829: "vm2 today", 858: "vm2 rule ceiling",
  995: "consensus-present rule ceiling", 1179: "vm plus the 2024 cohort", 1266: "vm plus 2025 and 2026 after R-VM",
  1464: "vm plus Pipeline-only 2011 to 2016 debuts", 1864: "vm rows for a two-hundredths E_refit floor",
  2667: "R-LV", 5529: "lv_dev plus R-LV after the look" };

function _lpN(v) { return v == null ? "-" : Number(v).toLocaleString("en-US"); }
function _lpPct(num, den) { return den ? `${(100 * Number(num) / Number(den)).toFixed(1)}%` : "-"; }
function _lpWar(p) { return _LP_PROVIDERS[p] ? `${_LP_PROVIDERS[p]} (${escapeHtml(p)})` : escapeHtml(String(p || "unknown")); }

// [2011, 2012, 2013, 2016] -> "2011 to 2013, 2016"
function _lpYears(ys) {
  const a = (Array.isArray(ys) ? ys : []).map(Number).filter(y => !isNaN(y)).sort((x, y) => x - y);
  if (!a.length) return "none";
  const runs = [];
  let s = a[0], p = a[0];
  a.slice(1).concat([NaN]).forEach(y => {
    if (y === p + 1) { p = y; return; }
    runs.push(s === p ? String(s) : `${s} to ${p}`);
    s = y; p = y;
  });
  return runs.join(", ");
}

// Sum the census frame rows of the given list vintages.
function _lpFrameAgg(rows, vintages) {
  const want = new Set((vintages || []).map(Number));
  const out = { rows: 0, hit: 0, pit: 0, how: {}, built: true };
  rows.filter(r => want.has(Number(r.vintage))).forEach(r => {
    const n = Number(r.rows || 0);
    out.rows += n;
    out[r.side] = (out[r.side] || 0) + n;
    if (r.built === false || !r.id_how) { out.built = false; return; }
    Object.entries(r.id_how).forEach(([k, v]) => { out.how[k] = (out.how[k] || 0) + Number(v || 0); });
  });
  return out;
}

function _lpFramesTable(c) {
  const fr = c.frame || {}, rows = Array.isArray(fr.rows) ? fr.rows : [];
  const routes = _LP_ROUTES.filter(([k]) => k !== "other" || rows.some(r => r.id_how && Number(r.id_how.other || 0) > 0));
  const res = fr.reserved_copied || {};
  const lines = [
    ["lv_dev", "development, spent", (fr.dev_totals || {}).vintages],
    ["R-LV", "reserved, never built", res.vintages],
    ["Later list vintages", "W3 not yet resolved", (fr.later_totals || {}).vintages],
  ].filter(l => Array.isArray(l[2]) && l[2].length).map(([name, role, vs]) => {
    const a = _lpFrameAgg(rows, vs);
    const head = `<td>${escapeHtml(name)}<br><span class="meth-sub">${escapeHtml(role)}</span></td><td>${escapeHtml(_lpYears(vs))}</td><td>${_lpN(a.rows)}<br><span class="meth-sub">${_lpN(a.hit)} hit / ${_lpN(a.pit)} pit</span></td>`;
    if (!a.built) {
      return `<tr>${head}<td colspan="${routes.length + 1}" class="meth-sub">identity not read: counts copied from ${escapeHtml(res.path || "the program document")} ${escapeHtml(res.section || "")}</td></tr>`;
    }
    const ok = _LP_RESOLVED.reduce((t, k) => t + Number(a.how[k] || 0), 0);
    return `<tr>${head}<td>${_lpN(ok)}<br><span class="meth-sub">${_lpPct(ok, a.rows)}</span></td>${routes.map(([k]) => `<td>${_lpN(a.how[k] || 0)}<br><span class="meth-sub">${_lpPct(a.how[k] || 0, a.rows)}</span></td>`).join("")}</tr>`;
  }).join("");
  if (!lines) return "";
  return `<div class="meth-table-title">List-vintage frames (W3 label): rows and how the outcome-blind resolver found each player</div>
    <div class="table-scroll-x"><table class="meth-table"><thead><tr><th>Frame</th><th>List vintages</th><th>Rows</th><th>Resolved</th>${routes.map(([, l]) => `<th>${escapeHtml(l)}</th>`).join("")}</tr></thead><tbody>${lines}</tbody></table></div>
    <p class="meth-note">${escapeHtml(fr.rule || "")}. A resolved row gains its pre-list minor league block; an ambiguous or no-candidate row is still scored, without that block.</p>`;
}

function _lpCohortTable(c) {
  const dc = c.debut_cohorts || {}, rows = Array.isArray(dc.rows) ? dc.rows : [];
  if (!rows.length) return "";
  const asOf = Number(String(c.generated_at || "").slice(0, 4));
  const inVm = r => !r.reserved_vm && Number(r.fangraphs_and_pipeline_both || 0) > 0
    && !isNaN(asOf) && asOf - Number(r.debut_cohort) >= _LP_VM_MIN_LAG;
  const vm = rows.filter(inVm);
  const sum = k => vm.reduce((t, r) => t + Number(r[k] || 0), 0);
  const vmYears = _lpYears(vm.map(r => r.debut_cohort));
  const rvm = rows.filter(r => r.reserved_vm);
  const body = rows.map(r => {
    const d = Number(r.debuts || 0);
    const tag = r.reserved_vm ? ` <span class="sacc-chip-warn">R-VM, counts only</span>` : (inVm(r) ? ` <span class="meth-sub">vm</span>` : "");
    return `<tr><td>${escapeHtml(String(r.debut_cohort))}${tag}</td><td>${_lpN(d)}</td>
      <td>${_lpN(r.in_window_consensus_read)}<br><span class="meth-sub">${_lpPct(r.in_window_consensus_read || 0, d)}</span></td>
      <td>${_lpN(r.fangraphs_and_pipeline_both)}<br><span class="meth-sub">${_lpPct(r.fangraphs_and_pipeline_both || 0, d)}</span></td>
      <td>${_lpN(r.with_record_id)}<br><span class="meth-sub">${_lpPct(r.with_record_id || 0, d)}</span></td>
      <td>${_lpN(r.with_career_war_row)}<br><span class="meth-sub">${_lpPct(r.with_career_war_row || 0, d)}</span></td></tr>`;
  }).join("");
  const lead = vm.length
    ? `<p class="meth-window"><strong>Vintage-matched frames, debut cohorts ${escapeHtml(vmYears)}:</strong> the vm2 rule (FanGraphs and MLB Pipeline both graded the player inside the debut year's preseason window) holds at most ${_lpN(sum("fangraphs_and_pipeline_both"))} rows, and the progress ledger above prints the rows vm2 scores. The consensus-present rule (vm3, not built) would hold at most ${_lpN(sum("in_window_consensus_read"))}.${rvm.length ? ` The reserved R-VM cohorts (${escapeHtml(_lpYears(rvm.map(r => r.debut_cohort)))}) print their counts and nothing else.` : ""}</p>` : "";
  return `${lead}<div class="table-scroll-x"><table class="meth-table"><thead><tr><th>Debut cohort</th><th>Debuts</th><th>Consensus read in window</th><th>FanGraphs and Pipeline both</th><th>Identity: debuts record id</th><th>Label row (career_war)</th></tr></thead><tbody>${body}</tbody></table></div>
    <p class="meth-note">${escapeHtml(dc.rule || "")}.</p>`;
}

function _lpJoinTable(c) {
  const ij = c.identity_join || {}, bp = ij.by_provider || {};
  const provs = Object.keys(bp);
  if (!provs.length) return "";
  const cols = [["debuts_json_id", "debuts record id"], ["override_asset_id", "override asset id"], ["no_id", "in debuts, no id"], ["key_not_in_debuts", "not in debuts"]];
  const body = provs.map(p => {
    const x = bp[p] || {}, n = Number(x.rows || 0), ir = x.id_route || {};
    return `<tr><td>${_lpWar(p)}</td><td>${_lpN(n)}</td>${cols.map(([k]) => `<td>${_lpN(ir[k] || 0)}<br><span class="meth-sub">${_lpPct(ir[k] || 0, n)}</span></td>`).join("")}</tr>`;
  }).join("");
  return `<div class="meth-table-title">The label join at the epoch: label rows by provider and identity route</div>
    <div class="table-scroll-x"><table class="meth-table"><thead><tr><th>Provider</th><th>Rows</th>${cols.map(([, l]) => `<th>${escapeHtml(l)}</th>`).join("")}</tr></thead><tbody>${body}</tbody></table></div>
    <p class="meth-note">${escapeHtml(ij.rule || "")}. The FanGraphs WAR feed joins on the MLBAM id, so a label row with no id by any route cannot take the new label at the epoch's join (FWAR_LABEL_EPOCH_GATE.md, precondition E2).</p>`;
}

// mde95(n) per frame type, drawn from the census: each reference is one measured
// point (filled), its sqrt-scaled curve is dashed, and the census's own listed
// row counts sit on the curves as hollow marks. Every number is the artifact's.
function _lpFloorChart(c) {
  const fc = c.floor_curve || {}, refs = Array.isArray(fc.references) ? fc.references : [];
  const z = Number(fc.z95), curve = fc.curve || {};
  const ns = (Array.isArray(fc.n) ? fc.n : []).map(Number).filter(n => n > 0);
  if (!refs.length || isNaN(z) || !ns.length) return "";
  const cols = ["var(--text-cyan)", "var(--text-amber)", "var(--text-violet)"];
  const dashes = ["6,4", "2,3", "9,3,2,3"];
  const narrow = (window.innerWidth || 1024) < 600;
  const W = narrow ? 340 : 580, H = narrow ? 240 : 260, ML = narrow ? 44 : 52, MR = narrow ? 10 : 16, MT = 14, MB = 40;
  const iW = W - ML - MR, iH = H - MT - MB;
  const allN = ns.concat(refs.map(r => Number(r.n_ref)).filter(n => n > 0));
  const lx0 = Math.log10(Math.min(...allN)) - 0.06, lx1 = Math.log10(Math.max(...allN)) + 0.06;
  const mde = (r, n) => z * Number(r.sd_ref) * Math.sqrt(Number(r.n_ref) / n);
  const yMax = Math.max(...refs.map(r => mde(r, Math.pow(10, lx0)))) * 1.05;
  const sx = n => ML + ((Math.log10(n) - lx0) / (lx1 - lx0)) * iW;
  const sy = v => MT + iH - (v / yMax) * iH;
  const raw = yMax / 5, mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const yStep = [1, 2, 5, 10].map(k => k * mag).find(s => s >= raw) || raw;
  const dec = Math.max(0, -Math.floor(Math.log10(yStep)));
  const grid = [];
  for (let v = 0; v <= yMax + yStep / 1000; v += yStep) {
    const y = sy(v).toFixed(1);
    grid.push(`<line x1="${ML}" y1="${y}" x2="${ML + iW}" y2="${y}" stroke="var(--border-light)" stroke-width="0.5" stroke-dasharray="2,3"/>`,
      `<text x="${ML - 6}" y="${y}" dy="3" text-anchor="end" font-size="9" fill="var(--text-tertiary)">${v.toFixed(dec)}</text>`);
  }
  const xt = [100, 200, 500, 1000, 2000, 5000].filter(n => Math.log10(n) >= lx0 && Math.log10(n) <= lx1).map(n =>
    `<line x1="${sx(n).toFixed(1)}" y1="${MT}" x2="${sx(n).toFixed(1)}" y2="${MT + iH}" stroke="var(--border-light)" stroke-width="0.5" stroke-dasharray="2,3"/><text x="${sx(n).toFixed(1)}" y="${MT + iH + 14}" text-anchor="middle" font-size="10" fill="var(--text-secondary)">${_lpN(n)}</text>`).join("");
  const series = refs.map((r, i) => {
    const col = cols[i % cols.length], pts = [];
    for (let k = 0; k <= 60; k++) {
      const n = Math.pow(10, lx0 + (lx1 - lx0) * k / 60);
      pts.push(`${sx(n).toFixed(1)},${sy(mde(r, n)).toFixed(1)}`);
    }
    const name = `${r.frame_type} ${r.estimator}, ${r.statistic}`;
    const pv = curve[r.id] || {};
    const hollow = ns.filter(n => pv[n] != null).map(n =>
      `<circle cx="${sx(n).toFixed(1)}" cy="${sy(Number(pv[n])).toFixed(1)}" r="3" fill="var(--bg-secondary)" stroke="${col}" stroke-width="1.4"><title>${escapeHtml(name)}: n ${_lpN(n)}${_LP_N_CAPTIONS[n] ? ` (${escapeHtml(_LP_N_CAPTIONS[n])})` : ""}, floor ${Number(pv[n]).toFixed(4)}, scaled from the measured point</title></circle>`).join("");
    const nr = Number(r.n_ref), my = mde(r, nr);
    const measured = `<circle cx="${sx(nr).toFixed(1)}" cy="${sy(my).toFixed(1)}" r="5" fill="${col}" stroke="var(--bg-secondary)" stroke-width="1"><title>measured: ${escapeHtml(name)}, n ${_lpN(nr)}${r.n_clusters_ref != null ? ` (${_lpN(r.n_clusters_ref)} players)` : ""}, bootstrap SD ${escapeHtml(String(r.sd_ref))}, floor ${my.toFixed(4)}; source ${escapeHtml(r.path || "")} (${escapeHtml(r.key || "")}), generated ${escapeHtml(String(r.generated_at || "").slice(0, 10))}</title></circle>`;
    return `<polyline points="${pts.join(" ")}" fill="none" stroke="${col}" stroke-width="1.6" stroke-dasharray="${dashes[i % dashes.length]}"/>${hollow}${measured}`;
  }).join("");
  const legend = refs.map((r, i) => `<span class="meth-legend-key"><span class="meth-legend-swatch" style="background:${cols[i % cols.length]};border-radius:50%;"></span>${escapeHtml(`${r.frame_type} frame, ${r.estimator}, ${r.statistic}`)}: measured at n ${_lpN(r.n_ref)} in ${escapeHtml(r.path || "")}</span>`).join("")
    + `<span class="meth-legend-key"><svg width="22" height="10" viewBox="0 0 22 10" aria-hidden="true"><line x1="1" y1="5" x2="21" y2="5" stroke="var(--text-secondary)" stroke-width="1.6" stroke-dasharray="4,3"/></svg>scaled by the square root of the row count</span>`
    + `<span class="meth-legend-key"><svg width="10" height="10" viewBox="0 0 10 10" aria-hidden="true"><circle cx="5" cy="5" r="3" fill="var(--bg-secondary)" stroke="var(--text-secondary)" stroke-width="1.4"/></svg>a row count the census lists</span>`;
  const head = refs.map(r => `<th>${escapeHtml(`${r.frame_type} ${r.estimator}, ${r.statistic}`)}</th>`).join("");
  const body = ns.slice().sort((a, b) => a - b).map(n => `<tr><td>${_lpN(n)}</td><td class="meth-sub">${escapeHtml(_LP_N_CAPTIONS[n] || "")}</td>${refs.map(r => {
    const v = (curve[r.id] || {})[n];
    return `<td>${v == null ? "-" : Number(v).toFixed(4)}</td>`;
  }).join("")}</tr>`).join("");
  return `<div class="meth-chart">
    <div class="meth-chart-title">The floor by frame size <span class="meth-sub">${escapeHtml(fc.formula || "")}; paired bootstrap, B 2000, player-clustered, one-sided z ${escapeHtml(String(fc.z95))}</span></div>
    <svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="Smallest resolvable difference by number of rows, per frame type, from the label pool census">
      ${grid.join("")}${xt}
      <line x1="${ML}" y1="${MT + iH}" x2="${ML + iW}" y2="${MT + iH}" stroke="var(--text-secondary)" stroke-width="1"/>
      <line x1="${ML}" y1="${MT}" x2="${ML}" y2="${MT + iH}" stroke="var(--text-secondary)" stroke-width="1"/>
      ${series}
      <text x="${ML + iW / 2}" y="${H - 6}" text-anchor="middle" font-size="10" fill="var(--text-tertiary)">rows in the frame (log scale)</text>
    </svg>
    <div class="meth-legend">${legend}</div>
    <p class="meth-note">Each curve is the smallest difference between eFV and PROSPX consensus that the registered read could resolve at that many rows of its frame type, not a result: no grade is scored here, a smaller floor is not a lead, and until a registered read clears its floor a difference inside it is a tie. ${escapeHtml(fc.rule || "")}.</p>
    <details class="scx-label-pool-floors"><summary>The floor at each row count the census lists</summary>
      <div class="table-scroll-x"><table class="meth-table"><thead><tr><th>Rows</th><th>What the count is</th>${head}</tr></thead><tbody>${body}</tbody></table></div>
      <p class="meth-note">Every value is the smallest difference the registered read could resolve at that n, copied from the census, and not a result.</p>
    </details>
  </div>`;
}

function _lpViewsTable(c) {
  const lv = c.label_views || {}, rows = Array.isArray(lv.rows) ? lv.rows : [];
  if (!rows.length) return "";
  const rt = (c.label || {}).resolved_through;
  const rt1 = (c.label || {}).resolved_through_plus_1;
  const cell = x => {
    if (!x) return "-";
    const ys = x.vintages || x.debut_cohorts || [];
    const n = x.rows != null ? `${_lpN(x.rows)} rows` : x.debuts != null ? `${_lpN(x.debuts)} debuts` : "";
    const resv = (x.reserved_lv_inside || []).length ? ` <span class="sacc-chip-warn">includes R-LV ${escapeHtml(_lpYears(x.reserved_lv_inside))}</span>`
      : (x.reserved_vm_inside || []).length ? ` <span class="sacc-chip-warn">includes R-VM ${escapeHtml(_lpYears(x.reserved_vm_inside))}</span>` : "";
    return `${escapeHtml(_lpYears(ys))}<br><span class="meth-sub">${n}</span>${resv}`;
  };
  const body = rows.map(r => `<tr><td><strong>${escapeHtml(String(r.label_view || "").replace(/_/g, "-"))}</strong><br><span class="meth-sub">${escapeHtml(r.unit === "vintage" ? "list vintage" : "debut cohort")}</span></td>
    <td class="meth-sub">${escapeHtml(r.definition || "")}</td><td class="meth-sub">${escapeHtml(r.resolves_when || "")}</td>
    <td>${cell(r.resolved_at_rt)}</td><td>${cell(r.resolved_at_rt_plus_1)}</td>
    <td>${cell(r.added_at_rt_plus_1)}</td><td class="meth-sub">${escapeHtml(r.standing || "")}</td></tr>`).join("");
  return `<div class="meth-table-title">Label views: which vintages and cohorts resolve at resolved_through ${escapeHtml(String(rt))} and ${escapeHtml(String(rt1))}</div>
    <div class="table-scroll-x"><table class="meth-table"><thead><tr><th>Label</th><th>Definition</th><th>Resolves when</th><th>At ${escapeHtml(String(rt))}</th><th>At ${escapeHtml(String(rt1))}</th><th>Added</th><th>Standing</th></tr></thead><tbody>${body}</tbody></table></div>
    <p class="meth-note">Counts only. A view that resolves more rows is not a better label: W3 scores the list vintages and the six-season label the debut cohorts, the shorter views are hazard components, a timing target or the R-VM look-1 label by design, and no new scoring label is registered. A change of label is never a gain in accuracy (FWAR_LABEL_EPOCH_GATE.md clause (l)).</p>`;
}

function _methLabelPoolSection() {
  _loadLabelPool();
  const c = _S.labelPool;
  if (!c || c.__error || !c.label) return "";
  const lb = c.label || {};
  const when = String(c.generated_at || "").slice(0, 10);
  const commit = String((c.code || {}).commit || "").slice(0, 8);
  const stamp = `<p class="meth-window"><strong>Census of ${escapeHtml(when)}:</strong> label WAR from ${_lpWar(lb.provider)}, resolved through ${escapeHtml(String(lb.resolved_through))} <span class="sacc-chip-warn">label ${escapeHtml(String(lb.id || lb.provider || ""))}</span>${commit ? ` <span class="meth-sub">code ${escapeHtml(commit)}</span>` : ""}. ${escapeHtml(c.epoch ? c.epoch.charAt(0).toUpperCase() + c.epoch.slice(1) + "." : "")} This panel counts rows and draws floors; it scores no grade, and a larger pool is not a lead.</p>`;
  return `<div class="scx-label-pool">
    <h2 class="meth-h" id="label-pool">The label pool: rows, identity and floors</h2>
    ${stamp}
    <div class="meth-chart">${_lpFramesTable(c)}</div>
    <div class="meth-chart">${_lpCohortTable(c)}</div>
    ${_lpFloorChart(c)}
    <div class="meth-chart">${_lpViewsTable(c)}</div>
    <details class="scx-label-pool-join"><summary>The label join at the epoch</summary><div class="meth-chart">${_lpJoinTable(c)}</div></details>
  </div>`;
}

// ---- Provisional track record (PV-08, PROVISIONAL_V2.md section 4) ----------
// Two tables, never pooled. SERVED: the provisional grade the site served (and the
// committed freezes of it), scored by provisional_track.py against the first source
// grades that arrived later; a frozen record is read only when its window closes, and
// until then the row prints its own "window open until <date>". BACKCAST: the
// forward-chained development read of the v2 first-grade model, labelled as such by its
// artifact and adjudicating nothing. Every number is read from the two artifacts at
// render time; none is typed here.
function _loadProvTrack() {
  if (_S.provTrack || _S.provTrackLoading) return;
  _S.provTrackLoading = true;
  const rerender = () => { if (_S.view === "source-comparison") renderSourceComparison(); };
  const get = p => p.then(r => (r.ok ? r.json() : null)).catch(() => null);
  Promise.all([
    get(fetch("/data/provisional_track_eval.json", { cache: "no-cache" })),
    get(fetch("/data/provisional_v2_eval.json", { cache: "no-cache" })),
  ]).then(([track, backcast]) => { _S.provTrack = { track, backcast }; rerender(); });
}

function _ptFmt(v, d) { return (v == null || isNaN(Number(v))) ? "-" : Number(v).toFixed(d); }
function _ptN(v) { return v == null ? "-" : Number(v).toLocaleString("en-US"); }

// The rows a reader should see: the latest row of every (leg, freeze, window).
function _ptLatestRows(t) {
  const rows = (t && Array.isArray(t.rows)) ? t.rows : [];
  const ids = new Set(Object.values((t && t.latest) || {}));
  const out = ids.size ? rows.filter(r => ids.has(r.run_id)) : rows.slice(-3);
  const legOrder = r => (r.leg === "prospective" ? 0 : 1);
  return out.slice().sort((a, b) => legOrder(a) - legOrder(b)
    || String(a.window_end || "").localeCompare(String(b.window_end || "")));
}

function _ptVerdict(r) {
  if (!r.verdict_readable) return `<span class="sacc-verdict-null">${escapeHtml(r.status || "window open")}</span>`;
  const c = r.claims || {};
  const lv = Object.entries(c.level || {}).map(([k, v]) => `level (${escapeHtml(k)}): ${v && v.claim ? "claim" : "no claim"}`);
  const sel = Object.entries(c.selection || {}).map(([k, v]) => `who (${escapeHtml(k)}): ${v && v.claim ? "claim" : "no claim"}`);
  const spent = r.leg === "served_backdated" ? `<br><span class="sacc-chip-warn">spent, adjudicates nothing</span>` : "";
  return `<span class="sacc-verdict-null">${[...lv, ...sel].join("; ") || "-"}</span>${spent}`;
}

function _ptServedTable(t) {
  const rows = _ptLatestRows(t);
  if (!rows.length) return "";
  const body = rows.map(r => {
    const res = r.result || {}, A = res.ANY || {}, sel = A.selection || {}, lev = A.level || {};
    const g = sel.grade || {}, p12 = sel.p_g12 || {}, lv = lev.grade || {};
    const who = `${_ptFmt(g.auc, 3)}${p12.auc != null ? `<br><span class="meth-sub">frozen P ${_ptFmt(p12.auc, 3)}</span>` : ""}`;
    const nul = (sel.null_level_rank || {}).auc;
    const level = lv.mae != null ? `${_ptFmt(lv.mae, 2)} vs ${_ptFmt(lv.mae_null_const, 2)}` : "-";
    const leg = r.leg === "served_backdated"
      ? `Served ${escapeHtml(r.frozen_at || "")}<br><span class="meth-sub">replayed to ${escapeHtml(r.window_end || "")}</span>`
      : `Frozen ${escapeHtml(r.frozen_at || "")}<br><span class="meth-sub">${escapeHtml(r.window || "")} window to ${escapeHtml(r.window_end || "")}</span>`;
    return `<tr><td>${leg}</td><td>${escapeHtml(r.scored_through || "")}</td><td>${_ptN(res.eligible)}</td>
      <td>${_ptN(A.graded_in_window)}</td><td>${who}</td><td>${_ptFmt(nul, 3)}</td>
      <td>${level}<br><span class="meth-sub">n ${_ptN(lev.n_first_fv)}</span></td>
      <td>${lev.median_lead_days != null ? _ptN(lev.median_lead_days) + " d" : "-"}</td><td>${_ptVerdict(r)}</td></tr>`;
  }).join("");
  return `<div class="meth-chart scx-provtrack-served">
    <div class="meth-table-title">SERVED: what the site showed, scored against the first grades that came later</div>
    <div class="table-scroll-x"><table class="meth-table"><thead><tr><th>Record</th><th>Scored through</th><th>Eligible</th><th>First graded</th><th>Who: AUC</th><th>Level-rank null</th><th>Level: MAE vs constant</th><th>Median lead</th><th>Verdict</th></tr></thead><tbody>${body}</tbody></table></div>
    <p class="meth-note">${escapeHtml(((r0) => r0 ? r0[0].toUpperCase() + r0.slice(1) + "." : "")((t.claim_rules || {}).read || ""))} ${escapeHtml(t.label_rule ? "Label: " + t.label_rule + "." : "")} Who: how well the grade ordered the players a label source graded first (AUC, where one half is a coin flip). Level: the mean miss against that first grade, beside a constant guess.</p>
  </div>`;
}

function _ptBackcastTable(b) {
  const bc = b && b.backcast;
  if (!bc) return "";
  const t1 = [], t2 = [];
  for (const anchor of ["oct", "jun"]) {
    const a = bc[anchor] || {};
    for (const [head, h] of Object.entries(a.T1 || {})) {
      const p = h.pooled || {};
      t1.push(`<tr><td>${escapeHtml(anchor === "oct" ? "Oct" : "Jun")}</td><td>${escapeHtml(head.replace("_", " "))}</td><td>${escapeHtml((h.test_anchors || []).join(", "))}</td><td>${_ptN(p.n)}</td><td>${_ptN(p.pos)}</td><td>${_ptFmt(p.auc, 3)}</td><td>${_ptFmt(p.null_level_rank_auc, 3)}</td><td>${_ptFmt(p.ap, 3)}</td></tr>`);
    }
    for (const [src, h] of Object.entries(a.T2 || {})) {
      const p = h.pooled || {};
      const ci = Array.isArray(p.mae_minus_const_ci95) ? `${_ptFmt(p.mae_minus_const_ci95[0], 3)} to ${_ptFmt(p.mae_minus_const_ci95[1], 3)}` : "-";
      t2.push(`<tr><td>${escapeHtml(anchor === "oct" ? "Oct" : "Jun")}</td><td>${escapeHtml(src === "FG" ? "FanGraphs" : src === "MLBP" ? "MLB Pipeline" : src)}</td><td>${_ptN(p.n)}</td><td>${_ptFmt(p.mae, 3)}</td><td>${_ptFmt(p.mae_const, 3)}</td><td>${_ptFmt(p.mae_minus_const, 3)}<br><span class="meth-sub">${ci}</span></td></tr>`);
    }
  }
  if (!t1.length && !t2.length) return "";
  return `<div class="meth-chart scx-provtrack-backcast">
    <div class="meth-table-title">${escapeHtml(b.label || "BACKCAST")}: the first-grade model on earlier anchors <span class="sacc-chip-warn">development read</span></div>
    ${t1.length ? `<div class="table-scroll-x"><table class="meth-table"><thead><tr><th>Anchor</th><th>Head</th><th>Test anchors</th><th>n</th><th>First graded</th><th>AUC</th><th>Level-rank null</th><th>AP</th></tr></thead><tbody>${t1.join("")}</tbody></table></div>` : ""}
    ${t2.length ? `<div class="table-scroll-x" style="margin-top:8px;"><table class="meth-table"><thead><tr><th>Anchor</th><th>Expected first grade</th><th>n</th><th>MAE</th><th>Constant MAE</th><th>Difference (CI95)</th></tr></thead><tbody>${t2.join("")}</tbody></table></div>` : ""}
    <p class="meth-note">${escapeHtml(b.label_note || "")}</p>
  </div>`;
}

function _methProvTrackSection() {
  _loadProvTrack();
  const s = _S.provTrack;
  if (!s || (!s.track && !s.backcast)) return "";
  const t = s.track || {};
  const served = s.track ? _ptServedTable(t) : "";
  const back = _ptBackcastTable(s.backcast);
  if (!served && !back) return "";
  // The one-line summary is the spent served replay's own numbers, when present.
  const sp = _ptLatestRows(t).find(r => r.leg === "served_backdated");
  let lead = "";
  if (sp) {
    const A = (sp.result || {}).ANY || {}, g = (A.selection || {}).grade || {}, lv = (A.level || {}).grade || {};
    lead = `<p class="meth-window">On the served ${escapeHtml(sp.frozen_at || "")} record replayed to ${escapeHtml(sp.window_end || "")}, the provisional grade ordered who a label source graded first at AUC ${_ptFmt(g.auc, 3)} against a level-rank null of ${_ptFmt(((A.selection || {}).null_level_rank || {}).auc, 3)} (${_ptN(A.graded_in_window)} first grades), and missed the first grade by ${_ptFmt(lv.mae, 2)} on average against ${_ptFmt(lv.mae_null_const, 2)} for a constant.${(lv.mae != null && lv.mae_null_const != null && Number(lv.mae) >= Number(lv.mae_null_const)
      && g.auc != null && Number(g.auc) > Number(((A.selection || {}).null_level_rank || {}).auc || 1)) ?" It finds who is next but not the level, so the PROSPX board lists players no source has graded in their own section, ordered by the chance of a first grade, and not in the eFV rank." : ""}</p>`;
  }
  return `<div class="source-comp-wrap scx-provtrack">
    <h2 class="meth-h" id="provisional-track-record">Provisional track record</h2>
    ${lead}${served}${back}
  </div>`;
}

function renderSourceComparison() {
  const el = document.getElementById("source-comparison-body");
  if (!el) return;
  // eFV progress ledger (same lazy idiom).
  _loadProgress();
  // eFV scoreboard matrix, under the ledger (same lazy idiom).
  _loadMatrix();
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
      ${_methProgressSection(bt)}
      ${_methMatrixSection(_S.progress, _S.matrix)}
      ${_methLabelPoolSection()}
      ${_scxGfxBarHTML()}
      <h2 class="meth-h">The full head-to-head</h2>
      <p class="meth-window">eFV is the primary grade, our outcome-grounded model. The test: a leakage-free, forward-chained backtest of eFV against the public sources (FanGraphs, MLB Pipeline) and the PROSPX consensus, scored on how well each grade ordered what prospects became. ${escapeHtml(bt.window.note)} ${_excludedSourcesClause(bt)}</p>
      ${_methEfvFindings(bt)}
      ${_methPerYearChart(bt)}
      <h3 class="meth-h3">Head-to-head: ranking skill + contributor AUC</h3>
      ${_methAccuracyChart(bt)}
      ${_methPerSourceCells(bt)}
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
  </div>` + _methProvTrackSection() + _methScoreboardHTML() + _methModelUpgrades();
  _mxBind();
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
    ${a.by_fv_tier_freeze && a.by_fv_tier_freeze.chip ? `<p class="meth-note"><span class="sacc-chip-warn" title="${escapeHtml(a.by_fv_tier_freeze.until || "")}">${escapeHtml(a.by_fv_tier_freeze.chip)}</span></p>` : ""}
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
      `<button class="chip${_SACC_TAB === k ? " active" : ""}" type="button" aria-pressed="${_SACC_TAB === k ? "true" : "false"}" data-sacc-tab="${escapeHtml(k)}">${escapeHtml(lbl)}</button>`).join("");
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

// ---- Library view ----------------------------------------------------------
// The Page Index (owner ask 2026-08-04; generated since LIBRARY_8,
// 2026-10-07): every page with its own address, each with a one-line purpose.
// The rows are written by build_site.page_index_groups() into the shell as an
// inert JSON script (#page-index-data): the full pages from the nav and the
// sitemap, the in-module views from a constant checked against each module's
// router, and the player cards. This view only reads and renders them. A
// hoisted function (not a const) on purpose: boot() can run during IIFE
// evaluation, and a const this far down would sit in the temporal dead zone at
// that moment (the _RATER_META lesson, 2026-06-10).
function _libraryGroups() {
  const el = document.getElementById("page-index-data");
  if (!el) return [];
  try {
    const groups = JSON.parse(el.textContent || "[]");
    return Array.isArray(groups) ? groups : [];
  } catch (e) {
    return [];
  }
}

function renderLibrary() {
  const el = document.getElementById("index-body");
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
  const groups = _libraryGroups();
  el.innerHTML = `<div class="source-comp-wrap">
    <div class="source-comp-eyebrow"><span class="scx-dot"></span>Page Index · every page with its own address</div>
    <h2 class="meth-h">The page index</h2>
    <p class="meth-note">Every page on eephus.io with its own address: the modules, the reference pages, the views inside each module you can link to, and the player cards.</p>
    <div class="meth-tables">${groups.length ? groups.map(group).join("") : '<p class="meth-note">The page list did not load with this page. Reload to try again.</p>'}</div>
  </div>`;
}

// ---- Source Updates view ---------------------------------------------------
// The dates each outlet published a list (owner ask 2026-10-02), read from
// the source updates payload that source_updates_export.py writes in nightly
// step d10g. One line per update in the owner's form "<Source> Update -
// <Month D, YYYY>", grouped by outlet, newest first, with the list names
// beneath. A list, not a table: every update is one <li>. The label and every
// long-form date come from the payload; this view formats no date of its own.
// Hoisted functions only (no const at this depth), for the TDZ reason the
// Library view gives above.
function _suSlug(s) {
  return "su-" + String(s).toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
}

function _suLabelHTML(u) {
  const lab = String(u.label || "");
  const i = lab.lastIndexOf(" - ");
  if (i < 0) return escapeHtml(lab);
  return `${escapeHtml(lab.slice(0, i + 3))}<time datetime="${escapeHtml(u.date)}">${escapeHtml(lab.slice(i + 3))}</time>`;
}

function _suListsText(u) {
  return (u.sets || []).map(s => {
    const lists = s.lists || [];
    let txt = s.family && lists.length > 1
      ? `${s.family}, ${lists.length} club lists`
      : lists.map(l => (l.length > 2 ? l[2] : l[0])).join("; ");
    if (s.basis === "changed") txt += " (changed since the previous nightly fetch)";
    else if (s.basis === "first_fetch") txt += " (first nightly fetch on record)";
    return txt;
  }).join("; ");
}

function _suRefetchedText(rows) {
  const groups = [];
  rows.forEach(r => {
    const name = r.family || r.name;
    let g = groups.find(x => x.name === name && x.last === r.last_fetch_long);
    if (!g) { g = { name, last: r.last_fetch_long, n: 0 }; groups.push(g); }
    g.n += 1;
  });
  return groups.map(g => `${g.name}${g.n > 1 ? `, ${g.n} club lists` : ""} (last fetched ${g.last})`).join("; ");
}

function _suSourceHTML(src, ups, refetched) {
  const S = window.EephusState;
  const id = _suSlug(src.source);
  const item = u => `<li class="su-item"><strong class="su-label">${_suLabelHTML(u)}</strong>` +
    `<div class="su-lists">${escapeHtml(_suListsText(u))}</div></li>`;
  let body;
  if (!ups.length) {
    const msg = "No dated update is on record for this outlet.";
    body = S ? S.html("unmeasured", msg, "su-state") : `<div class="state-message su-state">${msg}</div>`;
  } else {
    const head = ups.slice(0, 10), rest = ups.slice(10);
    body = `<ul class="sacc-leg-list su-list">${head.map(item).join("")}</ul>` + (rest.length
      ? `<details class="su-more"><summary>Show ${rest.length} earlier update${rest.length === 1 ? "" : "s"}</summary>` +
        `<ul class="sacc-leg-list su-list">${rest.map(item).join("")}</ul></details>`
      : "");
  }
  const n = src.n_updates || 0;
  const last = src.last_label
    ? `<p class="meth-window su-last">Last update: <strong>${_suLabelHTML({ label: src.last_label, date: src.last })}</strong></p>` : "";
  const count = `<p class="meth-note su-count">${n} update${n === 1 ? "" : "s"} · ${src.n_lists || 0} list${src.n_lists === 1 ? "" : "s"}` +
    `${src.first_long ? ` · first on record ${escapeHtml(src.first_long)}` : ""}</p>`;
  const re = refetched.length
    ? `<p class="meth-note su-refetched">Refetched each night under one name, so no publication date is on record: ${escapeHtml(_suRefetchedText(refetched))}.</p>` : "";
  return `<section class="su-src" aria-labelledby="${id}">` +
    `<h3 class="meth-h3 su-head" id="${id}">${escapeHtml(src.source)} <span class="gl-count">${n}</span></h3>` +
    `${last}${count}${body}${re}</section>`;
}

function renderSourceUpdates() {
  const el = document.getElementById("source-updates-body");
  if (!el) return;
  if (!_SU && !_SU_LOADING) {
    _SU_LOADING = true;
    fetch("/data/source_updates.json", { cache: "no-cache" })
      .then(r => (r.ok ? r.json() : null))
      .then(j => { _SU = j || { __error: true }; _SU_LOADING = false;
        if (_S.view === "source-updates") renderSourceUpdates(); })
      .catch(() => { _SU = { __error: true }; _SU_LOADING = false;
        if (_S.view === "source-updates") renderSourceUpdates(); });
  }
  const S = window.EephusState;
  const box = (kind, msg) => (S ? S.html(kind, msg, "su-state")
    : `<div class="state-message su-state"${kind === "failed" ? ' role="alert"' : ""}>${msg}</div>`);
  const shell = inner => `<div class="source-comp-wrap su-wrap">
    <div class="source-comp-eyebrow"><span class="scx-dot"></span>Source updates · when each outlet published</div>
    <h2 class="meth-h">Source Updates</h2>
    <p class="meth-note">One line per date an outlet published a new list, newest first, read from the dates our database stores each list under. A live list we fetch every night counts on the nights its players, ranks or grades changed.</p>
    ${inner}
  </div>`;
  const d = _SU;
  if (!d) { el.innerHTML = shell(box("loading", "Loading the source update dates...")); return; }
  if (d.__error || !Array.isArray(d.updates) || !Array.isArray(d.sources)) {
    el.innerHTML = shell(box("failed", "The source update dates could not be loaded." +
      '<div style="margin-top:12px;"><button class="chip" type="button" id="gl-su-retry">Retry</button></div>'));
    const rb = document.getElementById("gl-su-retry");
    if (rb) rb.onclick = () => { _SU = null; _SU_LOADING = false; renderSourceUpdates(); };
    return;
  }
  if (!d.sources.length) {
    el.innerHTML = shell(box("empty", "No source update is on record yet."));
    return;
  }
  const stamp = `<p class="meth-note su-stamp">Through ${escapeHtml(d.through_long || "")}` +
    `${d.built ? ` · built ${escapeHtml(String(d.built).replace("T", " ").replace(/:\d\dZ$/, " UTC"))}` : ""}</p>`;
  const jump = `<div class="filter-bar sacc-tabs su-jump" role="group" aria-label="Jump to an outlet"><span class="gl-microlabel">Outlet</span>` +
    d.sources.map(s => `<button class="chip" type="button" data-su-jump="${_suSlug(s.source)}">${escapeHtml(s.source)}</button>`).join("") +
    `</div>`;
  const blocks = d.sources.map(s => _suSourceHTML(s,
    d.updates.filter(u => u.source === s.source),
    (d.refetched || []).filter(r => r.source === s.source))).join("");
  el.innerHTML = shell(stamp + jump + blocks);
  el.querySelectorAll("[data-su-jump]").forEach(b => b.onclick = () => {
    const h = document.getElementById(b.dataset.suJump);
    if (h) { h.setAttribute("tabindex", "-1"); h.scrollIntoView({ block: "start" }); h.focus({ preventScroll: true }); }
  });
}

})();
