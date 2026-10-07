/* Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
 * Unauthorized copying of this file, via any medium is strictly prohibited
 * Proprietary and confidential
 * Written by Noah J. Dengler (@ARKNDJL), 2026 */

// =============================================================================
// eephus.io shared glossary runtime - data loader · ⌘K palette · term tooltips
// =============================================================================
// Loaded by every surface (editorial pages, /fa/, /glossary/, PROSPX). One
// fetch of data/glossary.json backs all three features; no surface holds its
// own copy of a definition.
//
//   window.EEPHUS_GLOSSARY        slug → legacy-shaped entry {name, short,
//                                 long, aliases, category, priority, formula,
//                                 example, visual_html, related, module}
//   window.EEPHUS_GLOSSARY_GROUPS category → display group
//   'eephus-glossary-ready'       window event fired once loaded
//   'eephus-glossary-failed'      window event fired when the fetch rejects
//                                 (window.EEPHUS_GLOSSARY_FAILED is then true)
// window.EEPHUS_QK_EXTRA optional hook: q => [{label, sub, href}] - 
//                                 PROSPX registers prospect search through it
//   window.EEPHUS_GL.wire(root)   scan a container for [data-gl] term spans:
//                                 sets aria-describedby + tooltip handlers.
//
// Extension contract for future modules: register terms in data/glossary.json
// (see build_glossary_data.py header for the schema), then wrap surfaced
// term text in <span class="g-term" data-gl="<slug>"> and call
// window.EEPHUS_GL.wire(container) after render. Nothing else.
(function () {
  "use strict";

  let READY = false;

  function esc(s) {
    return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  // ---- data layer ------------------------------------------------------------
  // TWO FILES (QHOP02, 2026-10-07). The full corpus is about 515 KB and only
  // /glossary/ and PROSPX read its long fields (methodology, formula, example,
  // visual, seeAlso). Every other page reads a term's name and short line, so
  // it fetches data/glossary_index.json (id, term, definition, aliases,
  // category, module, priority; written by build_site.write_glossary_index),
  // and only when the page has a term, a module calls wire(), or the reader
  // opens the palette or a tooltip. A missing index falls back to the full file.
  // CACHING. data/glossary.json is ~515KB and every surface on the site loads
  // this file, so its fetch is the heaviest recurring transfer we make. It used
  // to run with cache:"no-cache", which forces a revalidation round trip on
  // EVERY page view and re-downloads the whole payload whenever the build
  // touched it. It now rides a CONTENT-VERSIONED url under normal caching: the
  // hash is data/glossary.json's own content hash, injected by build_site.py
  // (window.EEPHUS_GL_DATA_VER, see _GL_DATA_VER there), so the browser serves
  // it from cache until the file actually changes and the changed file lands
  // under a url no cache has seen. Same freshness, one transfer per version.
  //
  // The eager fetch of the FULL file stays on /glossary/ and PROSPX: PROSPX
  // reads window.EEPHUS_GLOSSARY synchronously (_resolveGlossaryTerm on its
  // inline .g-term popovers, and two label builders), so a lazy map would
  // render those paths empty there.
  //
  // Pages that do not carry the global (the hand-authored ones, which get their
  // <script> tags from restamp_hand_authored_pages and never see build_site's
  // inline block) fall back to the unversioned url - still under default HTTP
  // caching, so still cheaper than the forced revalidation it replaces.
  const FULL = window.EEPHUS_GL_FULL === true
    || /^\/(glossary|library|prospx)(\/|$)/.test(location.pathname || "");
  function glossaryURL(file) {
    var v = null;
    try {
      v = window.EEPHUS_GL_DATA_VER || null;
      // Secondary source: a `d=` param on this script's own src, for any page
      // that would rather stamp the tag than emit a global.
      if (!v && document.currentScript && document.currentScript.src) {
        var m = /[?&]d=([A-Za-z0-9._-]+)/.exec(document.currentScript.src);
        if (m) v = m[1];
      }
    } catch (e) { v = null; }
    // The index is a pure function of glossary.json, so the full file's
    // content hash versions both urls.
    return "/data/" + file + (v ? "?v=" + encodeURIComponent(v) : "");
  }

  // The urls are fixed once here: document.currentScript is only set while
  // this file first runs, so a later reload() must not call glossaryURL() again.
  const GL_URL = glossaryURL("glossary.json");
  const GL_INDEX_URL = glossaryURL("glossary_index.json");
  let _loadStarted = false;
  function fetchJSON(url) {
    return fetch(url).then(r => { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); });
  }
  function load() {
    _loadStarted = true;
    window.EEPHUS_GLOSSARY_FAILED = false;
    (FULL ? fetchJSON(GL_URL) : fetchJSON(GL_INDEX_URL).catch(() => fetchJSON(GL_URL)))
      .then(d => {
        const map = {};
        for (const e of d.entries || []) {
          map[e.id] = { name: e.term, short: e.definition, long: e.methodology,
                        aliases: e.aliases || [], category: e.category,
                        priority: e.priority, formula: e.formula, example: e.example,
                        visual_html: e.visual, related: e.seeAlso || [],
                        module: e.module || [], shelf: e.shelf, origin: e.origin };
        }
        window.EEPHUS_GLOSSARY = map;
        window.EEPHUS_GLOSSARY_GROUPS = d.groups || {};
        READY = true;
        window.dispatchEvent(new Event("eephus-glossary-ready"));
      })
      // Glossary data is optional enrichment (tooltips + ⌘K palette). If it
      // can't load, degrade silently rather than logging to every visitor's
      // console - the site stays fully functional without it. The /glossary/
      // page has nothing to show without this data, so a failure is announced
      // (flag + 'eephus-glossary-failed') for it to paint a failed state with a
      // Retry that calls EEPHUS_GL.reload(). Tooltips and the palette ignore it.
      .catch(() => {
        window.EEPHUS_GLOSSARY_FAILED = true;
        window.dispatchEvent(new Event("eephus-glossary-failed"));
      });
  }
  // Start the fetch once, on first need (the full file at once on FULL pages).
  function ensureLoaded() { if (!_loadStarted) load(); }
  if (FULL) load();

  function resolve(q) {
    const map = window.EEPHUS_GLOSSARY || {};
    if (map[q]) return q;
    const lq = String(q || "").toLowerCase();
    for (const [slug, e] of Object.entries(map)) {
      if (e.name.toLowerCase() === lq) return slug;
      if ((e.aliases || []).some(a => a.toLowerCase() === lq)) return slug;
    }
    return null;
  }

  // ---- site-wide player index (lazy; first palette open) ----------------------
  // data/player_search.json (mlb_player_export.write_player_search) carries
  // key/name/team/pos/prospx for every MLB player AND every active PROSPX
  // prospect, so the palette finds players from any page. It is the five
  // fields of player_links.json's byKey the palette reads, without the byMlbam
  // copy (QHOP06); a deploy without it falls back to player_links.json.
  // On PROSPX itself the app registers richer prospect search via
  // EEPHUS_QK_EXTRA - there the built-in source only serves NON-prospect rows
  // (vets), so the two sources never duplicate a player.
  let _qkPlayers = null, _qkPlayersLoading = false;

  function qkRowsFromLinks(L) {
    return Object.values((L && L.byKey) || {}).map(r => r && [r.key, r.name, r.team, r.pos, r.prospx]);
  }
  function qkRowsFromSearch(S) {
    if (!S || !Array.isArray(S.rows)) throw new Error("no rows");
    const f = S.fields || [], at = k => f.indexOf(k);
    const ix = ["key", "name", "team", "pos", "prospx"].map(at);
    return S.rows.map(r => ix.map(i => (i < 0 ? "" : r[i])));
  }
  function qkLoadPlayers() {
    if (_qkPlayers || _qkPlayersLoading) return;
    _qkPlayersLoading = true;
    // The hub's parsed copy when the page has ALREADY asked for the identity
    // map, so a page that read it never downloads player data twice (QMLP09).
    const H = window.EEPHUS_HUB;
    const viaLinks = () => fetch("/data/player_links.json", { cache: "no-cache" })
      .then(r => (r.ok ? r.json() : null)).then(qkRowsFromLinks);
    (H && H.links && H.linksStarted && H.linksStarted()
      ? Promise.resolve(H.links()).then(qkRowsFromLinks)
      : fetch("/data/player_search.json", { cache: "no-cache" })
          .then(r => { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
          .then(qkRowsFromSearch)
          .catch(viaLinks))
      .then(list => {
        const rows = [];
        for (const row of list || []) {
          if (!row || !row[1]) continue;
          const [key, name, team, pos, prospx] = row;
          rows.push({
            name: name,
            search: String(name).toLowerCase(),
            sub: [pos, team].filter(Boolean).join(" · "),
            prospx: prospx || null,
            href: prospx
              ? "/prospx/#player=" + encodeURIComponent(prospx)
              : "/projections/#player=" + encodeURIComponent(key),
          });
        }
        _qkPlayers = rows;
        const ov = document.getElementById("qk-overlay");
        const inp = document.getElementById("qk-input");
        if (inp && ov && ov.classList.contains("is-open")) qkSearch(inp.value);
      })
      .catch(() => { _qkPlayers = []; })
      .finally(() => { _qkPlayersLoading = false; });
  }

  function qkPlayerMatches(lq) {
    if (!_qkPlayers || !_qkPlayers.length) return [];
    const hasExtra = typeof window.EEPHUS_QK_EXTRA === "function";
    const scored = [];
    for (const p of _qkPlayers) {
      if (hasExtra && p.prospx) continue;   // PROSPX's own source covers these
      let rank = null;
      if (p.search.startsWith(lq)) rank = 0;
      else if (p.search.split(/\s+/).some(w => w.startsWith(lq))) rank = 1;
      else if (p.search.includes(lq)) rank = 2;
      if (rank != null) scored.push([rank, p]);
    }
    scored.sort((a, b) => a[0] - b[0] || a[1].name.localeCompare(b[1].name));
    return scored.slice(0, 6).map(([, p]) => ({
      type: "player", kind: p.prospx ? "prospect" : "mlb",
      label: p.name, sub: p.sub, href: p.href,
    }));
  }

  // ---- ⌘K / Ctrl+K / "/" quick-search palette ---------------------------------
  let _qkActive = 0, _qkResults = [], _qkPrevFocus = null;

  function qkEnsure() {
    let ov = document.getElementById("qk-overlay");
    if (ov) return ov;
    ov = document.createElement("div");
    ov.id = "qk-overlay"; ov.className = "qk-overlay";
    // Combobox pattern (QHOA04): the input owns a listbox of option rows,
    // names the active one through aria-activedescendant, and a polite status
    // line reads the result count.
    ov.innerHTML = `<div class="qk-modal" role="dialog" aria-modal="true" aria-label="Quick search">
      <input id="qk-input" class="qk-input" type="text" placeholder="Search players, terms, metrics…" autocomplete="off" spellcheck="false" aria-label="Quick search" role="combobox" aria-autocomplete="list" aria-expanded="false" aria-controls="qk-results">
      <div id="qk-results" class="qk-results" role="listbox" aria-label="Results"></div>
      <div id="qk-status" class="gl-srdef" role="status" aria-live="polite"></div>
      <div class="qk-foot"><span><b>↵</b> open</span><span><b>↑ ↓</b> move</span><span><b>esc</b> close</span></div>
    </div>`;
    document.body.appendChild(ov);
    ov.addEventListener("click", e => { if (e.target === ov) qkClose(); });
    const inp = ov.querySelector("#qk-input");
    inp.addEventListener("input", () => qkSearch(inp.value));
    inp.addEventListener("keydown", e => {
      if (e.key === "ArrowDown") { e.preventDefault(); qkMove(1); }
      else if (e.key === "ArrowUp") { e.preventDefault(); qkMove(-1); }
      else if (e.key === "Enter") { e.preventDefault(); qkChoose(_qkActive); }
      else if (e.key === "Escape") { e.preventDefault(); qkClose(); }
      else if (e.key === "Tab") { e.preventDefault(); }  // trap focus on the input while open
    });
    return ov;
  }

  function qkOpen() {
    const ov = qkEnsure();
    _qkPrevFocus = document.activeElement;   // restore on close
    ensureLoaded();    // the term index, when the page had no term to load it
    qkLoadPlayers();   // lazy: the player index fetches on first open only
    ov.classList.add("is-open");
    const inp = ov.querySelector("#qk-input");
    inp.value = ""; qkSearch("");
    setTimeout(() => inp.focus(), 20);
  }
  function qkClose() {
    const ov = document.getElementById("qk-overlay");
    if (ov) ov.classList.remove("is-open");
    if (_qkPrevFocus && _qkPrevFocus.focus) _qkPrevFocus.focus();
    _qkPrevFocus = null;
  }

  function qkSearch(q) {
    q = (q || "").trim();
    const lq = q.toLowerCase();
    const out = [];
    if (q.length >= 2 && window.EEPHUS_GLOSSARY) {
      // rank: exact alias/abbrev > name prefix > alias prefix > name substr >
      // definition substr
      const scored = [];
      for (const [slug, e] of Object.entries(window.EEPHUS_GLOSSARY)) {
        const name = e.name.toLowerCase();
        const aliases = (e.aliases || []).map(a => a.toLowerCase());
        let rank = null;
        if (name === lq || aliases.includes(lq)) rank = 0;
        else if (name.startsWith(lq)) rank = 1;
        else if (aliases.some(a => a.startsWith(lq))) rank = 2;
        else if (name.includes(lq)) rank = 3;
        else if ((e.short || "").toLowerCase().includes(lq)) rank = 4;
        if (rank != null) scored.push([rank, e.priority ?? 99, slug, e]);
      }
      scored.sort((a, b) => a[0] - b[0] || a[1] - b[1]);
      for (const [, , slug, e] of scored.slice(0, 9)) {
        out.push({ type: "term", slug,
                   label: e.name,
                   sub: (e.short || "").slice(0, 96),
                   href: "/glossary/#g=" + encodeURIComponent(slug) });
      }
    }
    if (q.length >= 2 && typeof window.EEPHUS_QK_EXTRA === "function") {
      try {
        for (const r of window.EEPHUS_QK_EXTRA(q).slice(0, 6)) out.push(r);
      } catch (err) { /* extra source is best-effort */ }
    }
    if (q.length >= 2) {
      for (const r of qkPlayerMatches(lq)) out.push(r);
    }
    _qkResults = out;
    _qkActive = 0;
    qkRender(q);
  }

  function qkStatus(txt) {
    const s = document.getElementById("qk-status");
    if (s && s.textContent !== txt) s.textContent = txt;
  }
  function qkRender(q) {
    const el = document.getElementById("qk-results");
    const inp = document.getElementById("qk-input");
    if (!el) return;
    if (!q || q.length < 2 || !_qkResults.length) {
      if (inp) { inp.setAttribute("aria-expanded", "false"); inp.removeAttribute("aria-activedescendant"); }
    }
    if (!q || q.length < 2) {
      el.innerHTML = `<div class="qk-empty">Type 2+ characters - any player, metric, term, or model concept.</div>`;
      qkStatus("");
      return;
    }
    if (!_qkResults.length) {
      el.innerHTML = `<div class="qk-empty">No match - <a href="/glossary/">view the full Library</a></div>`;
      qkStatus("No results");
      return;
    }
    el.innerHTML = _qkResults.map((r, i) => `
      <div class="qk-row${i === _qkActive ? " is-active" : ""}" data-qk-i="${i}" id="qk-opt-${i}" role="option" aria-selected="${i === _qkActive}">
        <div class="qk-row-h"><span class="qk-row-name">${esc(r.label)}</span>
        <span class="qk-row-tag${r.type === "term" ? "" : " qk-row-tag-p"}">${esc(r.type === "term" ? "term" : (r.kind || ""))}</span></div>
        ${r.sub ? `<div class="qk-row-sub">${esc(r.sub)}</div>` : ""}
      </div>`).join("");
    el.querySelectorAll("[data-qk-i]").forEach(n => {
      n.onclick = () => qkChoose(+n.dataset.qkI);
      n.onmousemove = () => { _qkActive = +n.dataset.qkI; qkPaint(); };
    });
    if (inp) inp.setAttribute("aria-expanded", "true");
    qkPaint();
    const n = _qkResults.length;
    qkStatus(n + (n === 1 ? " result" : " results"));
  }
  function qkPaint() {
    document.querySelectorAll(".qk-row").forEach((n, i) => {
      n.classList.toggle("is-active", i === _qkActive);
      n.setAttribute("aria-selected", i === _qkActive ? "true" : "false");
    });
    const inp = document.getElementById("qk-input");
    if (inp && _qkResults.length) inp.setAttribute("aria-activedescendant", "qk-opt-" + _qkActive);
  }
  function qkMove(d) {
    if (!_qkResults.length) return;
    _qkActive = Math.max(0, Math.min(_qkResults.length - 1, _qkActive + d));
    qkPaint();
    const n = document.querySelector(`[data-qk-i="${_qkActive}"]`);
    if (n) n.scrollIntoView({ block: "nearest" });
  }
  function qkChoose(i) {
    const r = _qkResults[i];
    if (!r) return;
    qkClose();
    if (r.href) location.href = r.href;
  }

  function typingTarget(e) {
    const t = e.target;
    return t && (/^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName || "") || t.isContentEditable);
  }
  document.addEventListener("keydown", e => {
    if ((e.metaKey || e.ctrlKey) && (e.key === "k" || e.key === "K")) {
      if (typingTarget(e)) return;          // never steal Ctrl+K mid-typing
      e.preventDefault();
      const ov = document.getElementById("qk-overlay");
      if (ov && ov.classList.contains("is-open")) qkClose(); else qkOpen();
      return;
    }
    if (e.key === "/" && !typingTarget(e)) {
      const ov = document.getElementById("qk-overlay");
      if (!(ov && ov.classList.contains("is-open"))) { e.preventDefault(); qkOpen(); }
    }
  });
  document.addEventListener("click", e => {
    const t = e.target.closest("[data-qk-open]");
    if (t) { e.preventDefault(); qkOpen(); }
  });

  // ---- hover tooltips for [data-gl] term spans --------------------------------
  // Two timers: a SHOW delay (hover-intent on the term) and a HIDE grace. The
  // grace is the key fix - the tooltip is appended to <body>, not nested in the
  // term, so moving the pointer off the term toward the popup used to fire
  // mouseout and hide it instantly, making links inside (e.g. "Full entry")
  // unclickable. Now leaving the term only SCHEDULES a hide; entering the
  // tooltip cancels it. So the pointer can bridge the gap and interact with the
  // popup. Leaving either the term or the tooltip (re)starts the grace.
  let _tipShowTimer = null, _tipHideTimer = null, _tipFor = null;
  const _TIP_HIDE_GRACE = 220;

  function tipCancelHide() { clearTimeout(_tipHideTimer); _tipHideTimer = null; }
  function tipScheduleHide() {
    clearTimeout(_tipShowTimer); _tipShowTimer = null;   // a pending show is moot once we leave
    clearTimeout(_tipHideTimer);
    _tipHideTimer = setTimeout(tipHide, _TIP_HIDE_GRACE);
  }

  function tipEnsure() {
    let tip = document.getElementById("gl-tip");
    if (tip) return tip;
    tip = document.createElement("div");
    tip.id = "gl-tip"; tip.className = "gl-tip";
    tip.setAttribute("role", "tooltip");
    // Hovering the tooltip keeps it open; leaving it closes after the grace.
    // This is the "bridge" that makes the popup and its links reachable.
    tip.addEventListener("mouseenter", tipCancelHide);
    tip.addEventListener("mouseleave", tipScheduleHide);
    document.body.appendChild(tip);
    return tip;
  }
  function tipHide() {
    clearTimeout(_tipShowTimer); _tipShowTimer = null;
    clearTimeout(_tipHideTimer); _tipHideTimer = null;
    _tipFor = null;
    const tip = document.getElementById("gl-tip");
    if (tip) tip.classList.remove("is-open");
  }
  function tipShow(span) {
    const slug = resolve(span.dataset.gl);
    const e = slug && (window.EEPHUS_GLOSSARY || {})[slug];
    if (!e) return;
    const tip = tipEnsure();
    tip.innerHTML = `<div class="gl-tip-term">${esc(e.name)}</div>
      <div class="gl-tip-def">${esc(e.short)}</div>`;
    tip.classList.add("is-open");
    // collision-aware: below the term by default, above if no room; clamp X.
    const r = span.getBoundingClientRect();
    const tw = Math.min(300, window.innerWidth - 16);
    tip.style.maxWidth = tw + "px";
    const th = tip.offsetHeight;
    let top = r.bottom + 6 + window.scrollY;
    if (r.bottom + th + 12 > window.innerHeight && r.top - th - 6 > 0) {
      top = r.top - th - 6 + window.scrollY;
    }
    let left = r.left + window.scrollX;
    left = Math.max(8, Math.min(left, window.scrollX + window.innerWidth - tip.offsetWidth - 8));
    tip.style.top = top + "px";
    tip.style.left = left + "px";
    tipCancelHide();
    _tipFor = span;
  }
  // A term reached before the glossary is in shows once it lands.
  function tipShowReady(span) {
    ensureLoaded();
    if (READY) { tipShow(span); return; }
    window.addEventListener("eephus-glossary-ready", () => {
      if (span === document.activeElement || span.matches(":hover")) tipShow(span);
    }, { once: true });
  }
  document.addEventListener("mouseover", e => {
    const span = e.target.closest("[data-gl]");
    if (!span) return;
    ensureLoaded();
    tipCancelHide();                                   // re-entering the term aborts a pending close
    clearTimeout(_tipShowTimer);
    // 300 ms hover delay, with or without Reduce Motion (owner, 2026-10-01).
    _tipShowTimer = setTimeout(() => tipShowReady(span), 300);
  });
  document.addEventListener("mouseout", e => {
    if (e.target.closest && e.target.closest("[data-gl]")) tipScheduleHide();
  });
  document.addEventListener("focusin", e => {
    const span = e.target.closest && e.target.closest("[data-gl]");
    if (span) tipShowReady(span);
  });
  document.addEventListener("focusout", () => tipScheduleHide());
  // Escape closes an open term tooltip, whether hover or focus opened it
  // (WCAG 1.4.13, audit QCLA18).
  document.addEventListener("keydown", e => {
    if (e.key === "Escape" && _tipFor) tipHide();
  });
  // A scroll closes a hover tooltip. A tooltip opened by keyboard focus stays
  // with its term while the term is on screen: Tab onto a term below the fold
  // scrolls the page, and that scroll closed the tooltip it had just opened
  // (QHOA05).
  window.addEventListener("scroll", () => {
    if (!_tipFor) return;
    const span = _tipFor;
    if (span === document.activeElement) {
      const r = span.getBoundingClientRect();
      if (r.bottom > 0 && r.top < window.innerHeight) { tipShow(span); return; }
    }
    tipHide();
  }, { passive: true });
  // Touch devices can't hover, so the mouseover/focus tooltips above never
  // fire and term definitions were unreachable. On no-hover (touch) devices
  // only, tapping a [data-gl] term toggles its tooltip; tapping elsewhere
  // dismisses it. Gated to (hover: none) so mouse users keep pure hover.
  document.addEventListener("click", e => {
    const noHover = window.matchMedia && window.matchMedia("(hover: none)").matches;
    if (!noHover) return;
    const span = e.target.closest && e.target.closest("[data-gl]");
    if (span) {
      if (_tipFor === span) tipHide(); else tipShowReady(span);
    } else if (_tipFor && !(e.target.closest && e.target.closest("#gl-tip"))) {
      tipHide();
    }
  });

  // Screen readers get the definition inline: one hidden div per term,
  // referenced by every span for that term via aria-describedby.
  function wire(root) {
    const host = root || document;
    if (!READY && host.querySelector && !host.querySelector("[data-gl]")) return;
    ensureLoaded();
    const scan = () => {
      (root || document).querySelectorAll("[data-gl]").forEach(span => {
        const slug = resolve(span.dataset.gl);
        const e = slug && (window.EEPHUS_GLOSSARY || {})[slug];
        if (!e) return;
        span.classList.add("g-term");
        if (!span.hasAttribute("tabindex")) span.setAttribute("tabindex", "0");
        const did = "gl-def-" + slug;
        if (!document.getElementById(did)) {
          const d = document.createElement("div");
          d.id = did; d.className = "gl-srdef";
          d.textContent = e.name + ": " + e.short;
          document.body.appendChild(d);
        }
        span.setAttribute("aria-describedby", did);
      });
    };
    if (READY) scan();
    else window.addEventListener("eephus-glossary-ready", scan, { once: true });
  }

  // Every page's server-rendered masthead (.section-head) is wired here once,
  // so its glossary terms carry aria-describedby without each module calling
  // wire on it (audit QCLA18: /management/, /trademachine/, /hof/ and
  // /arbitration/ never did). wire() waits for the glossary when it is not in.
  try { document.querySelectorAll(".section-head").forEach(h => wire(h)); } catch (e) { /* optional */ }
  // Every other server-rendered term too: the editorial pages (/, /news/,
  // /history/) never called wire, so their terms had no aria-describedby
  // (QHOA05). A page with no term fetches nothing here.
  try { wire(document); } catch (e) { /* optional */ }
  // The palette re-runs its search when the term index lands after it opened.
  window.addEventListener("eephus-glossary-ready", () => {
    const ov = document.getElementById("qk-overlay");
    const inp = document.getElementById("qk-input");
    if (ov && inp && ov.classList.contains("is-open")) qkSearch(inp.value);
  });

  window.EEPHUS_GL = { open: qkOpen, wire, resolve, reload: load };
})();
