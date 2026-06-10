# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""One-time port generator for the unified Glossary & Methodology module.

Extracts the methodology prose, source-comparison backtest, How-to-Read
guide, per-term visualizations, and interactive teaching widgets from
prospx/index.html (owner decision: PORT to the standalone page) and emits:

  assets/glossary.js   — handwritten core (terms view, search, groups, A-Z,
                         router) + the ported blocks behind a small shim layer
  a .gl-app CSS block  — the prospx style sections those features need,
                         every selector re-scoped under .gl-app, appended to
                         assets/site.css between GLOSSARY-PORT markers

Like build_glossary_data.py this is provenance tooling: it runs once at port
time; assets/glossary.js is hand-maintained afterward.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).parent
SRC = (ROOT / "prospx" / "index.html").read_text(encoding="utf-8")
LINES = SRC.split("\n")


def slice_lines(a: int, b: int) -> str:
    """1-based inclusive line slice."""
    return "\n".join(LINES[a - 1:b])


def js_block() -> str:
    # function boundaries established in the Phase-0/port audit
    prose_charts = slice_lines(17995, 18252)     # _methProseHTML … _methTierTable
    guide = slice_lines(18260, 18364)            # renderGuide (+banner comment)
    viz_widgets = slice_lines(18366, 18523)      # _normCdf … _byId/_setHTML
    meth_sc = slice_lines(18617, 18742)          # _methInteractivesHTML … renderSourceComparison
    ported = "\n\n".join([prose_charts, guide, viz_widgets, meth_sc])
    # ---- adaptations -------------------------------------------------------
    ported = ported.replace('DATA._sourceBacktest', '_S.backtest')
    ported = ported.replace('DATA._btLoading', '_S.btLoading')
    ported = ported.replace('const base = DATA_URL.replace(/[^/]+$/, "");',
                            'const base = "/data/";')
    ported = ported.replace(
        'if (state.section === "glossary" && state.glossaryView === "source-comparison") renderSourceComparison();',
        'if (_S.view === "source-comparison") renderSourceComparison();')
    ported = ported.replace('PROSPX — Methodology · eephus.io/prospx',
                            'eephus.io — Methodology · eephus.io/glossary')
    return ported


CORE = r"""/* Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
 * Unauthorized copying of this file, via any medium is strictly prohibited
 * Proprietary and confidential
 * Written by Noah J. Dengler (@ARKNDJL), 2026 */

// =============================================================================
// eephus.io unified Glossary & Methodology app (/glossary/)
// =============================================================================
// Four views: Terms (search + group nav + A-Z index + entry cards) ·
// How to Read (annotated anatomy guide) · Methodology (derivations +
// interactive teaching widgets + PDF export) · Source Comparison (the
// empirical source-vs-source backtest). The guide/methodology/backtest
// renderers are PORTED from the retired PROSPX Glossary/Methodology tab
// (owner decision 2026-06-10); the data source for every definition is
// data/glossary.json via window.EEPHUS_GLOSSARY (assets/eephus-gl.js).
(function () {
  "use strict";

  const _S = { view: "terms", cat: "all", q: "", term: null,
               backtest: null, btLoading: false };
  let GL = {};         // legacy-shaped map: slug -> {name, short, long, ...}
  let GROUPS = {};     // category -> display group

  function escapeHtml(s) {
    return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }
  // Inline glossary link — same .g-term affordance as PROSPX; the shared
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
    if (p.has("view")) _S.view = p.get("view");
    if (p.has("cat")) _S.cat = p.get("cat");
    if (p.has("q")) _S.q = p.get("q");
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

  function entryCard(slug, e, expanded) {
    const altNames = (e.aliases || []).filter(a => a !== e.name && a.includes(" "));
    const fullName = altNames.length ? altNames.sort((a, b) => b.length - a.length)[0] : "";
    const more = [];
    if (e.long) more.push(`<div class="gl-meth">${e.long.split("\n\n").map(p => `<p>${escapeHtml(p)}</p>`).join("")}</div>`);
    if (e.formula) more.push(`<div class="gp-formula">${escapeHtml(e.formula)}</div>`);
    if (e.example) more.push(`<div class="gl-example"><span class="gl-microlabel">Example · </span>${escapeHtml(e.example)}</div>`);
    if (e.visual_html) more.push(`<div class="gl-microlabel" style="margin-top:8px;">Visual</div><div class="glossary-visual">${e.visual_html}</div>`);
    if (typeof _GLOSSARY_VIZ !== "undefined" && _GLOSSARY_VIZ[slug]) {
      let viz = ""; try { viz = _GLOSSARY_VIZ[slug](); } catch (err) { viz = ""; }
      if (viz) more.push(`<div class="gl-microlabel" style="margin-top:8px;">Visualization</div><div class="glossary-visual">${viz}</div>`);
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
        <span class="gl-badges">${moduleBadges(e)}</span>
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
      counts.all++;
      counts[grp] = (counts[grp] || 0) + 1;
      if (byGroup.has(grp)) byGroup.get(grp).push([slug, e]);
    }
    const chips = [`<button class="chip${_S.cat === "all" ? " active" : ""}" data-gl-cat="all">All <span class="gl-count">${counts.all}</span></button>`]
      .concat(groups.map(g =>
        `<button class="chip${_S.cat === g ? " active" : ""}" data-gl-cat="${escapeHtml(g)}">${escapeHtml(g)} <span class="gl-count">${counts[g] || 0}</span></button>`));
    document.getElementById("gl-cats").innerHTML = chips.join("");
    document.querySelectorAll("[data-gl-cat]").forEach(b => b.onclick = () => {
      _S.cat = b.dataset.glCat; syncToURL(); render();
    });
    // entries: alphabetical within the active scope
    const active = _S.cat === "all" ? groups : [_S.cat];
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

  // ---- router ----------------------------------------------------------------
  function render() {
    const ids = { terms: "glossary-rows", guide: "guide-body",
                  methodology: "methodology-body", "source-comparison": "source-comparison-body" };
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
__PORTED__

})();
"""


# ---- CSS port ----------------------------------------------------------------
# Prospx token names → site.css token bridge: the ported rules reference the
# app's palette (neon-cyan, font-sans/mono, up/down, radius). Aliased once on
# .gl-app so the rules run untouched under the editorial stylesheet.
TOKEN_BRIDGE = """.gl-app {
  --font-sans: var(--font-retro); --font-serif: var(--font-retro);
  --font-mono: var(--font-retro-mono); --font-retro-mono: var(--font-retro-mono);
  --neon-cyan: var(--accent-cyan); --neon-amber: var(--accent-gold);
  --neon-violet: #b47cff; --neon-orange: var(--accent-red);
  --up: var(--accent-green); --down: var(--accent-red);
  --radius-sm: 0; --radius-md: 0; --radius-lg: 0;
  font-family: var(--font-retro);
}
.gl-app .gl-card-head { display: flex; align-items: baseline; gap: 8px; flex-wrap: wrap; }
.gl-app .gl-fullname { font-size: 13px; color: var(--text-secondary); }
.gl-app .gl-badges { margin-left: auto; display: inline-flex; gap: 4px; }
.gl-app .gl-mod { font-family: var(--font-retro-mono); font-size: 8px; font-weight: 700;
  letter-spacing: 0.1em; padding: 2px 5px; border: 1px solid var(--border); color: var(--text-tertiary); }
.gl-app .gl-mod--fa { border-color: var(--accent-gold); }
.gl-app .gl-mod--prospx { border-color: var(--accent-cyan); }
.gl-app .gl-def { margin-top: 4px; font-size: 12.5px; color: var(--text-primary); line-height: 1.45; }
.gl-app .gl-meth p { margin: 0 0 8px; font-size: 12px; color: var(--text-secondary); line-height: 1.55; }
.gl-app .gl-example { font-size: 11.5px; color: var(--text-secondary); font-style: italic; margin-top: 6px; }
.gl-app .gl-microlabel { font-style: normal; color: var(--text-tertiary); font-size: 9px;
  letter-spacing: 0.08em; text-transform: uppercase; font-weight: 600; }
.gl-app .gl-relrow { margin-top: 8px; display: flex; flex-wrap: wrap; gap: 4px; align-items: center; }
.gl-app .gl-rel { font-family: var(--font-retro-mono); font-size: 10px; color: var(--accent-cyan);
  text-decoration: none; border: 1px solid var(--border-light); padding: 2px 8px; }
.gl-app .gp-more summary { cursor: pointer; font-size: 10px; color: var(--text-tertiary);
  letter-spacing: 0.06em; text-transform: uppercase; font-weight: 600; list-style: none; user-select: none; }
.gl-app .gp-more-body { margin-top: 6px; }
.gl-app .glossary-visual { padding: 10px 12px; border: 1px solid var(--border-light);
  background: var(--bg-secondary); display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin-top: 4px; }
.gl-app #gl-az { display: flex; flex-wrap: wrap; gap: 2px; font-family: var(--font-retro-mono);
  font-size: 11px; margin: 6px 0 10px; }
.gl-app #gl-az a, .gl-app #gl-az span { padding: 2px 5px; text-decoration: none; color: var(--text-secondary); }
.gl-app #gl-az a:hover { color: var(--text-primary); background: var(--bg-tertiary); }
.gl-app .gl-az-off { opacity: 0.3; }
.gl-app .gl-count { color: var(--text-tertiary); font-size: 10px; margin-left: 3px; }
.gl-app .gl-intro p { max-width: 78ch; font-size: 13px; line-height: 1.6; color: var(--text-secondary); margin: 0 0 10px; }
.gl-app .state-message { text-align: center; padding: 3rem 1rem; color: var(--text-secondary); }
.gl-app input.gl-search { width: 100%; max-width: 460px; padding: 7px 10px; font-family: var(--font-retro-mono);
  font-size: 13px; background: var(--bg-secondary); border: 1px solid var(--border); color: var(--text-primary); }
.gl-app .filter-bar { display: flex; flex-wrap: wrap; gap: 4px; align-items: center; margin: 8px 0;
  padding: 8px 10px; background: var(--bg-secondary); border: 1px solid var(--border); }
.gl-app button.chip { font-family: var(--font-retro); font-size: 12px; padding: 4px 10px; cursor: pointer;
  border: 1px solid var(--border); background: var(--bg-secondary); color: var(--text-secondary); }
.gl-app button.chip.active { color: var(--text-primary); border-color: var(--accent-gold); font-weight: 700; }
"""


def _rescope(selectors: str) -> str:
    outs = []
    for sel in selectors.split(","):
        s = sel.strip()
        if not s:
            continue
        if s.startswith("body.printing-meth") or s.startswith("@"):
            outs.append(s)
        elif s.startswith("[data-theme="):
            # [data-theme="dark"] .x → [data-theme="dark"] .gl-app .x
            outs.append(re.sub(r'^(\[data-theme="[a-z]+"\])\s*', r"\1 .gl-app ", s))
        else:
            outs.append(".gl-app " + s)
    return ", ".join(outs)


def _scope_css(css: str) -> str:
    out_rules = []
    i = 0
    while i < len(css):
        m = re.compile(r"([^{}]+)\{").match(css, i)
        if not m:
            break
        head = m.group(1).strip()
        if head.startswith("@media") or head.startswith("@keyframes"):
            j = m.end()
            depth = 1
            while depth and j < len(css):
                if css[j] == "{":
                    depth += 1
                elif css[j] == "}":
                    depth -= 1
                j += 1
            inner = css[m.end():j - 1]
            if head.startswith("@keyframes"):
                out_rules.append(head + " {" + inner + "}")
            else:
                inner_scoped = re.sub(r"([^{}]+)\{",
                                      lambda mm: _rescope(mm.group(1)) + " {", inner)
                out_rules.append(head + " {" + inner_scoped + "}")
            i = j
        else:
            j = css.index("}", m.end())
            out_rules.append(_rescope(head) + " {" + css[m.end():j].rstrip() + " }")
            i = j + 1
    return "\n".join(out_rules)


def css_blocks() -> tuple[str, str]:
    """(.gl-app-scoped port, unscoped qk palette block)."""
    guide = slice_lines(4184, 4219)
    palette = slice_lines(4220, 4246)
    widgets = slice_lines(4247, 4290)
    meth = slice_lines(4291, 4424)
    cards = slice_lines(7157, 7255)
    scoped = TOKEN_BRIDGE + _scope_css("\n".join([guide, widgets, meth, cards]))
    return scoped, palette


def main() -> None:
    ported = js_block()
    js = CORE.replace("__PORTED__", ported)
    (ROOT / "assets" / "glossary.js").write_text(js, encoding="utf-8")
    print("wrote assets/glossary.js:", len(js) // 1024, "KB")
    scoped, palette = css_blocks()
    marker_a = "/* ── GLOSSARY-PORT (generated; .gl-app-scoped prospx styles) ─────────── */"
    marker_b = "/* ── /GLOSSARY-PORT ───────────────────────────────────────────────────── */"
    site = (ROOT / "assets" / "site.css").read_text(encoding="utf-8")
    if marker_a in site:
        site = site[:site.index(marker_a)] + site[site.index(marker_b) + len(marker_b):]
    block = (marker_a + "\n" + scoped +
             "\n/* qk quick-search palette (site-wide; unscoped — overlays any page) */\n"
             + palette + "\n" + marker_b + "\n")
    site = site.rstrip() + "\n\n" + block
    (ROOT / "assets" / "site.css").write_text(site, encoding="utf-8")
    print("appended glossary CSS:", len(block) // 1024, "KB")


if __name__ == "__main__":
    main()
