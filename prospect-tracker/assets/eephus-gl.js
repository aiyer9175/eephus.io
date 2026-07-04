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
  fetch("/data/glossary.json", { cache: "no-cache" })
    .then(r => { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
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
    // console - the site stays fully functional without it.
    .catch(() => {});

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
  // data/player_links.json carries name/team/pos for every MLB player AND
  // every active PROSPX prospect, so the palette finds players from any page.
  // On PROSPX itself the app registers richer prospect search via
  // EEPHUS_QK_EXTRA - there the built-in source only serves NON-prospect rows
  // (vets), so the two sources never duplicate a player.
  let _qkPlayers = null, _qkPlayersLoading = false;

  function qkLoadPlayers() {
    if (_qkPlayers || _qkPlayersLoading) return;
    _qkPlayersLoading = true;
    fetch("/data/player_links.json", { cache: "no-cache" })
      .then(r => (r.ok ? r.json() : null))
      .then(L => {
        const rows = [];
        for (const row of Object.values((L && L.byKey) || {})) {
          if (!row || !row.name) continue;
          rows.push({
            name: row.name,
            search: String(row.name).toLowerCase(),
            sub: [row.pos, row.team].filter(Boolean).join(" · "),
            prospx: row.prospx || null,
            href: row.prospx
              ? "/prospx/#player=" + encodeURIComponent(row.prospx)
              : "/projections/#player=" + encodeURIComponent(row.key),
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
    ov.innerHTML = `<div class="qk-modal" role="dialog" aria-modal="true" aria-label="Quick search">
      <input id="qk-input" class="qk-input" type="text" placeholder="Search players, terms, metrics…" autocomplete="off" spellcheck="false" aria-label="Quick search">
      <div id="qk-results" class="qk-results"></div>
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

  function qkRender(q) {
    const el = document.getElementById("qk-results");
    if (!el) return;
    if (!q || q.length < 2) {
      el.innerHTML = `<div class="qk-empty">Type 2+ characters - any player, metric, term, or model concept.</div>`;
      return;
    }
    if (!_qkResults.length) {
      el.innerHTML = `<div class="qk-empty">No match - <a href="/glossary/">view the full glossary</a></div>`;
      return;
    }
    el.innerHTML = _qkResults.map((r, i) => `
      <div class="qk-row${i === _qkActive ? " is-active" : ""}" data-qk-i="${i}">
        <div class="qk-row-h"><span class="qk-row-name">${esc(r.label)}</span>
        <span class="qk-row-tag${r.type === "term" ? "" : " qk-row-tag-p"}">${esc(r.type === "term" ? "term" : (r.kind || ""))}</span></div>
        ${r.sub ? `<div class="qk-row-sub">${esc(r.sub)}</div>` : ""}
      </div>`).join("");
    el.querySelectorAll("[data-qk-i]").forEach(n => {
      n.onclick = () => qkChoose(+n.dataset.qkI);
      n.onmousemove = () => { _qkActive = +n.dataset.qkI; qkPaint(); };
    });
  }
  function qkPaint() {
    document.querySelectorAll(".qk-row").forEach((n, i) =>
      n.classList.toggle("is-active", i === _qkActive));
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
  document.addEventListener("mouseover", e => {
    const span = e.target.closest("[data-gl]");
    if (!span) return;
    tipCancelHide();                                   // re-entering the term aborts a pending close
    clearTimeout(_tipShowTimer);
    const delay = matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 300;
    _tipShowTimer = setTimeout(() => tipShow(span), delay);
  });
  document.addEventListener("mouseout", e => {
    if (e.target.closest && e.target.closest("[data-gl]")) tipScheduleHide();
  });
  document.addEventListener("focusin", e => {
    const span = e.target.closest && e.target.closest("[data-gl]");
    if (span) tipShow(span);
  });
  document.addEventListener("focusout", () => tipScheduleHide());
  window.addEventListener("scroll", () => { if (_tipFor) tipHide(); }, { passive: true });
  // Touch devices can't hover, so the mouseover/focus tooltips above never
  // fire and term definitions were unreachable. On no-hover (touch) devices
  // only, tapping a [data-gl] term toggles its tooltip; tapping elsewhere
  // dismisses it. Gated to (hover: none) so mouse users keep pure hover.
  document.addEventListener("click", e => {
    const noHover = window.matchMedia && window.matchMedia("(hover: none)").matches;
    if (!noHover) return;
    const span = e.target.closest && e.target.closest("[data-gl]");
    if (span) {
      if (_tipFor === span) tipHide(); else tipShow(span);
    } else if (_tipFor && !(e.target.closest && e.target.closest("#gl-tip"))) {
      tipHide();
    }
  });

  // Screen readers get the definition inline: one hidden div per term,
  // referenced by every span for that term via aria-describedby.
  function wire(root) {
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

  window.EEPHUS_GL = { open: qkOpen, wire, resolve };
})();
