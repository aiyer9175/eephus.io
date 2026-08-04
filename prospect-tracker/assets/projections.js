/* Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
 * Unauthorized copying of this file, via any medium is strictly prohibited
 * Proprietary and confidential
 * Written by Noah J. Dengler (@ARKNDJL), 2026 */

// =============================================================================
// eephus.io MLB Projections app (/projections/)
// =============================================================================
// The FA module's projection engine (proj_lgbm_v1) applied to the whole
// league, plus PROSPX prospects joining at their projected ETA. One sidecar
// (data/mlb_projections.json, proj_export.py); standalone by design - no
// PROSPX boot payload, no FA sidecars. Every row carries floor/mean/ceiling
// probability buckets; veteran surplus exists ONLY on salary-known seasons.
(function () {
  "use strict";

  const EM_DASH = " - ";
  let DATA = null;

  // Mirror of PROSPX's formatMetric, character-identical to the copy in fa.js -
  // same precision rules, same null token, same -0 collapse. This surface had
  // its OWN pair of one-off formatters instead, which is how the three MLB
  // boards ended up with three number vocabularies that agreed by luck rather
  // than by contract. The local mirror (rather than a shared import) is the
  // established convention here: fa.js keeps one for the same reason, so no
  // module surface has to pull in the PROSPX script. test_number_format_parity
  // pins the two copies identical so they cannot drift again.
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
      case "moneyM":   return (z < 0 ? "-" : "") + "$"
                            + (abs >= 100 ? abs.toFixed(0) : abs.toFixed(1)) + "M";
      case "pct":      return z.toFixed(1) + "%";
      default:         return String(z);
    }
  }

  const fmtWar = v => formatMetric(v, "war");
  // Signature kept at one argument: every call site here passes dollars and
  // wants the millions form. The old body emitted "-$1.6M" for negatives,
  // which `moneyM` now does too (it used to drop the sign).
  const money = usd => (usd == null ? EM_DASH : formatMetric(usd / 1e6, "moneyM"));
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
    if (!org) return "";
    const slug = ESPN_SLUGS[org] || String(org).toLowerCase();
    return `<img class="fa-logo" src="https://a.espncdn.com/i/teamlogos/mlb/500/${slug}.png" alt="${esc(org)}" loading="lazy" onerror="this.replaceWith('${esc(org)}')">`;
  }

  function posGroup(pos) {
    const head = String(pos || "").toUpperCase().split("/")[0].trim();
    if (["SP", "SP2", "P", "LHP", "RHP"].includes(head)) return "SP";
    if (["RP", "CL", "SIRP", "MIRP"].includes(head)) return "RP";
    if (head === "C") return "C";
    if (["1B", "2B", "3B", "SS", "IF"].includes(head)) return "IF";
    if (["LF", "CF", "RF", "OF"].includes(head)) return "OF";
    if (head === "DH" || head === "H") return "DH";
    return "IF";
  }

  // WAR heat class - color escalates with the season's own WAR.
  function warClass(w) {
    if (w == null) return "";
    if (w >= 4) return " proj-war-elite";
    if (w >= 2.5) return " proj-war-good";
    if (w >= 1) return " proj-war-avg";
    return " proj-war-low";
  }

  // Projected RATE lines (vets only - fa_projection.rate_path arrays; the
  // prospect outcome model is FV-anchored and carries no rate machinery,
  // so prospect cells render a dash under a rate metric).
  const RATE_META = {
    wrc:  { label: "wRC+", fmt: v => String(Math.round(v)), hi: [140, 115, 90],
            tip: "projected wRC+ (park-neutral, 100 = league average)" },
    woba: { label: "wOBA", fmt: v => v.toFixed(3).replace(/^0(?=\.)/, ""), hi: [0.370, 0.340, 0.310],
            tip: "projected wOBA (Marcel components aged along the engine's curves)" },
    fip:  { label: "FIP", fmt: v => v.toFixed(2), lo: [3.00, 3.75, 4.50],
            tip: "projected FIP (lower is better)" },
  };
  function rateAt(m, t) {
    const arr = state.cells === "wrc" ? m.wrc
      : state.cells === "woba" ? m.woba
      : state.cells === "fip" ? m.fip : null;
    return arr ? (arr[t] ?? null) : null;
  }
  function rateClass(v) {
    const mm = RATE_META[state.cells];
    if (!mm || v == null) return "";
    if (mm.hi) return v >= mm.hi[0] ? " proj-war-elite" : v >= mm.hi[1] ? " proj-war-good"
      : v >= mm.hi[2] ? " proj-war-avg" : " proj-war-low";
    return v <= mm.lo[0] ? " proj-war-elite" : v <= mm.lo[1] ? " proj-war-good"
      : v <= mm.lo[2] ? " proj-war-avg" : " proj-war-low";
  }

  const state = { src: "all", pos: "all", team: "all", contract: "all", age: "all", q: "", sort: "warTotal",
                  dir: -1, limit: 100, player: null, view: "players", cmp: [],
                  // Season-cell metric: war (default) | wrc | woba | fip - the board's
                  // per-season cells re-render on the projected RATE line when toggled.
                  cells: "war",
                  // Talent-map scatter axes (user-pickable).
                  sx: "age", sy: "warY1",
                  // Team Outlook column sort: teamSort = column key (null keeps
                  // the export's roster-WAR order); teamDir = 1 natural / -1 reversed.
                  teamSort: null, teamDir: 1,
                  // Team Outlook slate: "proj" = the 2027 projection (default),
                  // "now" = the dark-launched Current (2026) view (#now=1 soak).
                  teamMode: "proj", teamModeTouched: false };
  let DETAIL = null;            // data/mlb_player_detail.json, lazy
  let DETAIL_LOADING = false;
  let FIELDING = null;          // data/mlb_fielding_positions.json, lazy
  let FIELDING_LOADING = false;
  let PITCHLB = null;           // {byMlbam:{...}} from the /mlbstats/ leaderboards, lazy
  let PITCHLB_LOADING = false;
  let SWINGD = null;            // data/swing_delta.json (bat-tracking year-over-year), lazy
  let SWINGD_LOADING = false;

  function syncFromURL() {
    const p = new URLSearchParams(location.hash.slice(1));
    state.player = p.get("player") || null;
    state.view = ["teams", "accountability"].includes(p.get("view")) ? p.get("view") : "players";
    state.cmp = (p.get("cmp") || "").split(",").filter(Boolean).slice(0, 2);
    if (p.has("src")) state.src = p.get("src");
    if (p.has("pos")) state.pos = p.get("pos");
    if (p.has("team")) state.team = p.get("team");
    if (p.has("contract")) state.contract = p.get("contract");
    if (p.has("age")) state.age = p.get("age");
    // Whitelist like view above: an arbitrary #cells= value (typo, truncated
    // share link) would crash renderTable's header template on
    // RATE_META[state.cells].label - fall back to the WAR default instead.
    if (p.has("cells") && ["war", "wrc", "woba", "fip"].includes(p.get("cells"))) state.cells = p.get("cells");
    if (p.has("sx")) state.sx = p.get("sx");
    if (p.has("sy")) state.sy = p.get("sy");
    if (p.has("q")) state.q = p.get("q");
    if (p.has("sort")) state.sort = p.get("sort");
  }
  function syncToURL() {
    const p = new URLSearchParams();
    if (state.player) p.set("player", state.player);
    if (state.view !== "players") p.set("view", state.view);
    if (state.cmp.length) p.set("cmp", state.cmp.join(","));
    if (state.src !== "all") p.set("src", state.src);
    if (state.pos !== "all") p.set("pos", state.pos);
    if (state.team !== "all") p.set("team", state.team);
    if (state.contract !== "all") p.set("contract", state.contract);
    if (state.age !== "all") p.set("age", state.age);
    if (state.cells !== "war") p.set("cells", state.cells);
    if (state.sx !== "age") p.set("sx", state.sx);
    if (state.sy !== "warY1") p.set("sy", state.sy);
    if (state.q) p.set("q", state.q);
    if (state.sort !== "warTotal") p.set("sort", state.sort);
    const h = p.toString();
    history.replaceState(null, "", h ? `#${h}` : location.pathname);
  }

  // Season-aligned WAR for a row: vets start at first_season; prospects at
  // their ETA (pre-ETA seasons are MiLB time - rendered as such, never 0).
  // The WAR shown on the board/cells is the "playing-time-held" (if-healthy)
  // path - the 70th-percentile outcome - so a star's out-years read at their
  // healthy level rather than the attrition-discounted expected value. Surplus
  // and all valuation still price off the expected value (m.war / surNpv), never
  // this display series. Vets carry warPTH; prospects fall back to war.
  // The player's full remaining surplus, in raw dollars. `surTotal`
  // (2026-08-03) is the balance of the season in progress plus the NPV of every
  // controlled season after it; `surNpv` counted only seasons from
  // DATA.first_season on, so a contract ending this year showed no surplus at
  // all even while its club still controlled the player for months.
  //
  // The trade board prices surTotal, and the two surfaces are required to agree
  // per player (test_calibration_vintage: "the same player is worth the same on
  // every surface"), so this page reads the same field. Prospect rows are
  // unaffected: they carry surNpv only.
  function surOf(m) {
    if (!m) return null;
    if (m.surTotal != null) return m.surTotal;
    return m.surNpv != null ? m.surNpv : null;
  }
  function warAt(m, t) {
    const arr = (m.warPTH && m.warPTH.length) ? m.warPTH : m.war;
    if (m.src === "prospect") {
      const off = t - (m.eta - DATA.first_season);
      return off >= 0 && off < (arr || []).length ? arr[off] : null;
    }
    return (arr || [])[t] ?? null;
  }
  function bandAt(m, t, which) {
    // Prefer the prime-path bands so a prospect's displayed (prime) cell never
    // sits outside its own band; vets fall back to their expected bands.
    const arr = which === "lo" ? (m.warPTHP10 || m.warP10) : (m.warPTHP90 || m.warP90);
    if (!arr) return null;
    if (m.src === "prospect") {
      const off = t - (m.eta - DATA.first_season);
      return off >= 0 && off < arr.length ? arr[off] : null;
    }
    return arr[t] ?? null;
  }

  // The DISPLAYED 5-year (windowed, ETA-aligned) WAR total, so the board sorts on
  // the same number the Total column shows. Prospects get the in-window sum only
  // (a late-ETA prospect's off-window prime years do NOT float him up the board);
  // vets keep their full if-healthy total (already 5-year, truncated at export).
  function warShown(m) {
    if (m.src === "prospect") {
      let s = null;
      for (let t = 0; t < DATA.horizon; t++) {
        const w = warAt(m, t);
        if (w != null) s = (s == null ? 0 : s) + w;
      }
      return s;
    }
    return m.warTotalPTH ?? m.warTotal;
  }

  // Age filter bands: [lo, hi) on the row's decimal age.
  const AGE_FILTER_BANDS = { u23: [0, 23], "23-26": [23, 27], "27-30": [27, 31],
                             "31-34": [31, 35], "35+": [35, 99] };
  function posMatches(m) {
    if (state.pos === "all") return true;
    const g = posGroup(m.pos);
    // H / P side roll-ups mirror the PROSPX position filter; two-way rows
    // match both sides.
    if (state.pos === "H") return m.twoWay || !["SP", "RP"].includes(g);
    if (state.pos === "P") return m.twoWay || ["SP", "RP"].includes(g);
    return g === state.pos;
  }
  function ageMatches(m) {
    if (state.age === "all") return true;
    const b = AGE_FILTER_BANDS[state.age];
    return !!b && m.age != null && m.age >= b[0] && m.age < b[1];
  }
  function rows() {
    const all = (DATA.vets || []).concat(DATA.prospects || []);
    const q = state.q.trim().toLowerCase();
    return all.filter(m =>
      (state.src === "all" || m.src === state.src)
      && posMatches(m)
      && (state.team === "all" || m.team === state.team)
      && (state.contract === "all" || contractStatus(m).key === state.contract)
      && ageMatches(m)
      && (!q || (m.name || "").toLowerCase().includes(q)));
  }

  function sortRows(list) {
    const k = state.sort;
    const val = m => {
      if (k === "age") return m.age ?? 99;
      if (k === "sur") return surOf(m) ?? -1e15;
      if (k === "warTotal") return warShown(m) ?? -99;  // sort by the DISPLAYED 5yr total (prospects: in-window only)
      // Name and rank became sortable when the board moved to cards (2026-07-30).
      // Name sorts as a string, so it is compared case-insensitively and the
      // direction chip reads A-Z on the first click rather than Z-A.
      if (k === "name") return String(m.name || "").toLowerCase();
      // "rank" means the board's own current order, which is what the row
      // number shows. Sorting by it is the way back to the default view after
      // clicking through other columns.
      if (k === "rank") return warShown(m) ?? -99;
      if (k.startsWith("y")) {
        const t = Number(k.slice(1));
        if (state.cells !== "war") {
          // Season headers sort the ACTIVE cell metric. FIP is lower-better:
          // negate so the default descending click puts the best arms first.
          const v = rateAt(m, t);
          if (v == null) return -1e9;
          return state.cells === "fip" ? -v : v;
        }
        return warAt(m, t) ?? -99;
      }
      return m[k] ?? -99;
    };
    return list.slice().sort((a, b) => state.dir * (val(a) > val(b) ? 1 : val(a) < val(b) ? -1 : 0));
  }

  // User-tweakable scatter: BOTH axes are pickable (age, year-1 WAR, 5y WAR,
  // year-1 wOBA / wRC+ / FIP), so the one chart answers many questions -
  // aging landscape, rate-vs-WAR agreement, arm value maps. Colored by
  // contract control status. Honors the current filters; dots link to players.
  const SCATTER_AXES = {
    age:      { label: "Age",                  get: m => m.age },
    warY1:    { label: "Year-1 WAR",           get: m => warAt(m, 0) },
    warTotal: { label: "5y WAR (shown)",       get: m => warShown(m) },
    woba:     { label: "Year-1 wOBA (proj)",   get: m => (m.woba || [])[0] ?? null, f3: true },
    wrc:      { label: "Year-1 wRC+ (proj)",   get: m => (m.wrc || [])[0] ?? null },
    fip:      { label: "Year-1 FIP (proj)",    get: m => (m.fip || [])[0] ?? null, f2: true },
  };
  function _axFmt(ax, v) {
    return ax.f3 ? v.toFixed(3).replace(/^0(?=\.)/, "") : ax.f2 ? v.toFixed(2)
      : Math.abs(v) >= 100 ? String(Math.round(v)) : (Math.round(v * 10) / 10).toString();
  }
  // Talent-map dot tint by contract control status - one shared map for the
  // scatter dots AND the legend row under the axis pickers, so they never drift.
  const CONTRACT_DOT_COLORS = { signed: "var(--accent-green)", expiring: "var(--accent-gold)",
                                controlled: "var(--accent-cyan)", prospect: "var(--text-tertiary)" };
  function projWarMap(list) {
    const ax = SCATTER_AXES[state.sx] || SCATTER_AXES.age;
    const ay = SCATTER_AXES[state.sy] || SCATTER_AXES.warY1;
    const pts = list.map(m => ({ m, x: ax.get(m), y: ay.get(m) }))
      .filter(p => p.x != null && p.y != null && isFinite(p.x) && isFinite(p.y));
    if (pts.length < 6) return "";
    const W = 760, H = 400, PAD = 52;
    const xs = pts.map(p => p.x), ys = pts.map(p => p.y);
    const _pad = (lo, hi) => { const d = (hi - lo) || 1; return [lo - 0.05 * d, hi + 0.05 * d]; };
    const [x0, x1] = _pad(Math.min(...xs), Math.max(...xs));
    const [y0, y1] = _pad(Math.min(...ys), Math.max(...ys));
    const px = v => PAD + (v - x0) / (x1 - x0) * (W - 2 * PAD);
    const py = v => (H - PAD) - (v - y0) / (y1 - y0) * (H - 2 * PAD);
    const ticks = (lo, hi) => Array.from({ length: 6 }, (_, i) => lo + (hi - lo) * i / 5);
    const grid = ticks(x0, x1).map(v => `<line x1="${px(v).toFixed(1)}" y1="${PAD}" x2="${px(v).toFixed(1)}" y2="${H - PAD}" stroke="var(--border-light)" stroke-width="0.5"/><text x="${px(v).toFixed(1)}" y="${H - PAD + 14}" text-anchor="middle" font-size="9" fill="var(--text-tertiary)">${_axFmt(ax, v)}</text>`).join("")
      + ticks(y0, y1).map(v => `<line x1="${PAD}" y1="${py(v).toFixed(1)}" x2="${W - PAD}" y2="${py(v).toFixed(1)}" stroke="var(--border-light)" stroke-width="0.5"/><text x="${PAD - 6}" y="${(py(v) + 3).toFixed(1)}" text-anchor="end" font-size="9" fill="var(--text-tertiary)">${_axFmt(ay, v)}</text>`).join("");
    const dots = pts.map(({ m, x, y }) => {
      const c = CONTRACT_DOT_COLORS[contractStatus(m).key] || "var(--text-tertiary)";
      const href = m.src === "prospect" ? `/prospx/#player=${encodeURIComponent(m.key)}` : `#player=${encodeURIComponent(m.key)}`;
      return `<a href="${href}"><circle cx="${px(x).toFixed(1)}" cy="${py(y).toFixed(1)}" r="3.5" fill="${c}" fill-opacity="0.7" stroke="${c}" stroke-width="0.5"><title>${esc(m.name)} - ${esc(ax.label)} ${_axFmt(ax, x)} · ${esc(ay.label)} ${_axFmt(ay, y)}</title></circle></a>`;
    }).join("");
    return `<svg viewBox="0 0 ${W} ${H}" class="proj-warmap-svg" role="img" aria-label="${esc(ay.label)} versus ${esc(ax.label)} scatter">
      <text x="${PAD}" y="20" font-size="11" font-weight="700" fill="var(--text-secondary)">${pts.length} players · ${esc(ay.label)} vs ${esc(ax.label)}</text>
      <text x="${W / 2}" y="${H - 4}" text-anchor="middle" font-size="10" fill="var(--text-tertiary)">${esc(ax.label)}</text>
      <text x="14" y="${H / 2}" text-anchor="middle" font-size="10" fill="var(--text-tertiary)" transform="rotate(-90 14 ${H / 2})">${esc(ay.label)}</text>
      ${grid}${dots}
    </svg>`;
  }

  // Prospect grade language: eFV (the outcome-grounded model grade, exported as
  // fv with fv_source="xfv") leads wherever the payload carries it, matching the
  // PROSPX board's eFV-primary treatment; consensus FV is the fallback for the
  // players eFV abstains on. Rounding rules: eFV displays round-to-NEAREST,
  // consensus FV displays CEILING (fvCeil).
  function prospectGrade(m) {
    if (m.fv_source === "xfv") return `eFV ${Math.round(m.fv)}`;
    return `FV ${EEPHUS_HUB.fvCeil(m.fv)}`;
  }
  function tagFor(m) {
    if (m.src === "prospect") {
      const gradeNote = m.fv_source === "xfv"
        // "rank-mapped to the 20-80 scale" described the QUANTILE map, which was
        // retired from display on 2026-07-25. proj_export now serves the board
        // grade (value_framework.outcome_implied_fv off the pooled outcome
        // curve), so this copy was describing a grade the row no longer carries.
        ? `Graded on eFV (outcome-grounded model grade off the pooled outcome curve)${m.consensus_fv != null ? `; consensus FV ${EEPHUS_HUB.fvCeil(m.consensus_fv)}` : ""}. `
        : "";
      return `<span class="proj-tag proj-tag-prospect" title="PROSPX prospect - outcome-model projection (P(bucket|FV) × calibrated trajectories) starting at the projected ETA. ${gradeNote}Floor/ceiling are the 10th/90th-percentile OUTCOME buckets (${esc(m.bucketLo || "?")} → ${esc(m.bucketHi || "?")}); P(bust) ${m.pBust != null ? (m.pBust * 100).toFixed(0) + "%" : "?"}.">${prospectGrade(m)} · ETA ${m.eta}</span>`;
    }
    return m.twoWay
      ? `<span class="proj-tag" title="Two-way profile - projected on the larger recent exposure only (disclosed simplification).">two-way</span>` : "";
  }

  // Contract control status, at the granularity the data supports. Spotrac
  // gives the guaranteed-salary schedule but no service time or option flags,
  // so the pre-arb-vs-arb split and the option kinds (which the Free Agency
  // module DOES tag: club / player / mutual / opt-out) are not modelled for the
  // league-wide vet pool - the cost-controlled bucket says so plainly rather
  // than guessing.
  function contractStatus(m) {
    const first = DATA.first_season;
    if (m.src === "prospect")
      return { key: "prospect", label: "Prospect", cls: "proj-ct-prospect",
        tip: "Pre-MLB - the six cost-controlled years (3 pre-arb + 3 arb) start at debut" };
    if (m.thru && m.thru > first)
      return { key: "signed", label: `Signed · ${m.thru}`, cls: "proj-ct-signed",
        tip: `Guaranteed contract through ${m.thru}${m.aav ? ` at ${money(m.aav)}/yr` : ""}` };
    if (m.thru && m.thru === first)
      return { key: "expiring", label: `Expiring ${m.thru}`, cls: "proj-ct-expiring",
        tip: "Final guaranteed year - reaches arbitration or free agency after this season" };
    return { key: "controlled", label: "No multi-year deal", cls: "proj-ct-controlled",
      tip: "No guaranteed multi-year deal on file: pre-arbitration or arbitration salary (the service-time split needs data not fetched league-wide), or an unsigned free agent (so it is not necessarily cost-controlled). FA-class members carry their option / UFA kind in the Free Agency module." };
  }

  // The three top-level projection views + the unified-glossary chip (mirrors
  // the FA module's glossary link, deep-linked to the Platform & Methodology
  // group). Rendered into the filter bar on every view so switching is one
  // click and the glossary is always at hand.
  const GLOSSARY_CHIP = ` <a class="chip" href="/glossary/#cat=${encodeURIComponent("Platform & Methodology")}" title="Every projection and methodology term, defined - in the unified site glossary"><span class="chip-glyph" aria-hidden="true">§</span>Glossary</a>`;
  function viewChips(active) {
    const c = (v, label, title) =>
      `<button class="chip${active === v ? " active" : ""}" data-pv="${v}"${title ? ` title="${esc(title)}"` : ""}>${label}</button>`;
    return c("players", "Players")
      + c("teams", "Team Outlook", "First-season roster WAR roll-up -> projected wins (pre-free-agency frame)")
      + c("accountability", "Model Accountability", "How these projections are validated: held-out backtests, model verdicts, methodology")
      + GLOSSARY_CHIP;
  }

  function render() {
    const root = document.getElementById("proj-rows");
    const bar = document.getElementById("proj-filters");
    const banner = document.getElementById("proj-banner");
    if (!root || !DATA) return;
    if (state.player) { renderPlayer(state.player); return; }
    if (state.cmp.length === 2) { renderCompare(); return; }
    if (state.view === "teams") { renderTeams(); return; }
    if (state.view === "accountability") { renderAccountability(); return; }
    const first = DATA.first_season;
    const teams = [...new Set((DATA.vets || []).map(m => m.team).filter(Boolean))].sort();

    banner.innerHTML = `<div class="fa-note fa-sources">
      ${DATA.generated_at ? `data as of ${esc(String(DATA.generated_at))} &middot; ` : ""}${DATA.n_vets} veterans (the <span data-gl="fa_projection_engine">FA projection engine</span>, league-wide)
      &middot; ${DATA.n_prospects} prospects (<span data-gl="proj_buckets">outcome buckets</span> from their PROSPX ETA)
      &middot; seasons priced at the ${first} ex-ante <span data-gl="winter_dpw">$/WAR</span> ${money(DATA.dpw_usd)},
      escalating ${(DATA.dpw_infl * 100).toFixed(0)}%/yr
      &middot; WAR shown is the <strong>playing-time-held</strong> (if-healthy) path; <span data-gl="contract_surplus">surplus</span> prices the attrition-discounted expected value, only where a real contract exists
      &middot; <button class="chip egfx-chip" id="proj-board-gfx" title="Generate a shareable graphic (theme-aware, multiple formats)"><span class="egfx-chip-glyph" aria-hidden="true">&#9636;</span>Generate GFX</button></div>`;
    const gfxBtn = document.getElementById("proj-board-gfx");
    if (gfxBtn) gfxBtn.onclick = () => {
      if (window.EEPHUS_GFX) window.EEPHUS_GFX.open(_projBoardSpec(sortRows(rows()).slice(0, 50)));
    };

    const chip = (label, key, field) =>
      `<button class="chip${state[field] === key ? " active" : ""}" data-pf="${field}:${key}">${label}</button>`;
    bar.innerHTML = viewChips("players") + `
      <span class="filter-label proj-fgroup">Source</span>
      ${chip("All", "all", "src")}${chip("Veterans", "vet", "src")}${chip("Prospects", "prospect", "src")}
      <span class="filter-label proj-fgroup">Pos</span>
      ${[["All", "all"], ["H", "H"], ["P", "P"], ["SP", "SP"], ["RP", "RP"], ["C", "C"], ["IF", "IF"], ["OF", "OF"], ["DH", "DH"]].map(([l, p]) => chip(l, p, "pos")).join("")}
      <span class="filter-label proj-fgroup">Age</span>
      ${[["All", "all"], ["U23", "u23"], ["23-26", "23-26"], ["27-30", "27-30"], ["31-34", "31-34"], ["35+", "35+"]].map(([l, k]) => chip(l, k, "age")).join("")}
      <span class="filter-label proj-fgroup">Contract</span>
      ${[["All", "all"], ["Signed", "signed"], ["Expiring", "expiring"], ["Cost-ctrl", "controlled"], ["Prospect", "prospect"]].map(([l, k]) => chip(l, k, "contract")).join("")}
      <span class="filter-label proj-fgroup">Team</span>
      <select id="proj-team" class="proj-select">
        <option value="all">All teams</option>
        ${teams.map(t => `<option value="${t}"${state.team === t ? " selected" : ""}>${t}</option>`).join("")}
      </select>
      <span class="filter-label proj-fgroup" title="What the per-season cells show: projected WAR (default) or the projected rate line (veterans; the prospect outcome model is FV-anchored and carries no rate paths)">Cells</span>
      ${[["WAR", "war"], ["wRC+", "wrc"], ["wOBA", "woba"], ["FIP", "fip"]].map(([l, k]) => chip(l, k, "cells")).join("")}
      <input id="proj-q" class="proj-search" type="search" placeholder="Search players…" value="${esc(state.q)}" aria-label="Search players">`;
    bar.querySelectorAll("[data-pv]").forEach(b => b.onclick = () => {
      state.view = b.dataset.pv; syncToURL(); render();
    });
    bar.querySelectorAll("[data-pf]").forEach(b => b.onclick = () => {
      const [field, key] = b.dataset.pf.split(":");
      state[field] = key; state.limit = 100; syncToURL(); render();
    });
    const sel = document.getElementById("proj-team");
    if (sel) sel.onchange = () => { state.team = sel.value; state.limit = 100; syncToURL(); render(); };
    const inp = document.getElementById("proj-q");
    if (inp) {
      inp.oninput = () => { state.q = inp.value; state.limit = 100; syncToURL(); renderTable(); };
    }
    renderTable();
    if (window.EEPHUS_GL) window.EEPHUS_GL.wire(banner);
  }

  // ---- mini trend line -------------------------------------------------------
  // SOURCE OF TRUTH: assets/fa.js `miniTrendSVG` (extracted there out of
  // dpwTrendChart, the module's $/WAR-by-winter rail chart). Same shape, same
  // contract: var() colour tokens only so it is right in both themes, endpoint
  // VALUE labels rather than an unlabelled squiggle, and an invisible fat hit
  // circle over every point so each one is hoverable. Duplicated rather than
  // imported for the reason formatMetric is duplicated at the top of this file:
  // these surfaces share no module system and /projections/ deliberately loads
  // no other module's script.
  //
  // pts: [{ v: <number>, t: <hover text> }, ...]. Returns "" under two points,
  // which is the caller's cue to render nothing rather than a one-dot chart.
  function miniTrendSVG(pts, opt) {
    const o = opt || {};
    const use = (pts || []).filter(p => p && Number.isFinite(Number(p.v)));
    if (use.length < 2) return "";
    const W = o.w || 92, H = o.h || 28;
    const PT = o.pt != null ? o.pt : 10, PB = o.pb != null ? o.pb : 4;
    const PL = o.pl != null ? o.pl : 4, PR = o.pr != null ? o.pr : 4;
    const vs = use.map(p => Number(p.v));
    let lo = Math.min(...vs), hi = Math.max(...vs);
    const span = (hi - lo) || 1;
    lo -= span * 0.08; hi += span * 0.08;
    const x = i => PL + i * (W - PL - PR) / (use.length - 1);
    const y = v => PT + (hi - v) * (H - PT - PB) / (hi - lo);
    const col = o.color || "var(--accent-cyan)";
    const fmt = o.fmt || (v => String(v));
    const line = use.map((p, i) => `${x(i).toFixed(1)},${y(p.v).toFixed(1)}`).join(" ");
    const dots = use.map((p, i) => i === use.length - 1
      ? `<circle cx="${x(i).toFixed(1)}" cy="${y(p.v).toFixed(1)}" r="2.2" fill="${col}"/>`
      : `<circle cx="${x(i).toFixed(1)}" cy="${y(p.v).toFixed(1)}" r="1.3" fill="${col}" fill-opacity="0.75"/>`).join("");
    const hits = use.map((p, i) =>
      `<circle cx="${x(i).toFixed(1)}" cy="${y(p.v).toFixed(1)}" r="6" fill="transparent"><title>${esc(p.t || "")}</title></circle>`).join("");
    const first = use[0], last = use[use.length - 1];
    const firstLbl = `<text x="${PL}" y="${Math.max(7, y(first.v) - 4).toFixed(1)}" font-size="7" fill="var(--text-tertiary)">${esc(fmt(first.v))}</text>`;
    const lastLbl = `<text x="${W - PR}" y="${Math.max(7, y(last.v) - 4).toFixed(1)}" text-anchor="end" font-size="7.5" font-weight="700" fill="var(--text-secondary)">${esc(fmt(last.v))}</text>`;
    return `<svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" class="proj-minitrend" role="img" aria-label="${esc(o.aria || "trend")}">
      <polyline points="${line}" fill="none" stroke="${col}" stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round"/>
      ${dots}${firstLbl}${lastLbl}${hits}</svg>`;
  }

  function renderTeams() {
    const root = document.getElementById("proj-rows");
    const bar = document.getElementById("proj-filters");
    const banner = document.getElementById("proj-banner");
    const rows = DATA.team_outlook || [];
    bar.innerHTML = viewChips("teams");
    bar.querySelectorAll("[data-pv]").forEach(b => b.onclick = () => {
      state.view = b.dataset.pv; syncToURL(); render();
    });
    // Banner + GFX button track the Team Outlook view (the Players banner is
    // rebuilt in render()), so Generate GFX exports the team board you're on.
    if (banner) {
      const bControl = rows.some(r => r.lockedPct != null);
      const frame = `Current-season (${DATA.first_season}) roster bWAR &rarr; projected wins`
        + (bControl ? ` &middot; core control = cost-controlled WAR locked up for the future` : "");
      banner.innerHTML = `<div class="fa-note fa-sources">
        ${DATA.generated_at ? `data as of ${esc(String(DATA.generated_at))} &middot; ` : ""}${frame}
        &middot; <button class="chip egfx-chip" id="proj-teams-gfx" title="Generate a shareable graphic of the Team Outlook board"><span class="egfx-chip-glyph" aria-hidden="true">&#9636;</span>Generate GFX</button></div>`;
      const tgfx = document.getElementById("proj-teams-gfx");
      if (tgfx) tgfx.onclick = () => {
        if (window.EEPHUS_GFX && rows.length) window.EEPHUS_GFX.open(_teamOutlookBoardSpec(rows));
      };
    }
    if (!rows.length) {
      root.innerHTML = `<div class="state-message">This view is temporarily unavailable. Check back shortly.</div>`;
      return;
    }
    // Org-dashboard columns (the retired /teams/ page, merged here
    // 2026-06-12): farm rank + grade score, net active prospect surplus,
    // top prospect, and the cross-module links. Rows without a baked
    // farm block (older exports) degrade to the original columns.
    const hasFarm = rows.some(r => r.farm);
    const hasControl = rows.some(r => r.lockedPct != null || (Array.isArray(r.byYear) && r.byYear.length));
    // System Duration / Window Alignment: dark by default pre-launch; opt in
    // with #window=1 for the soak, then flip WINDOW_DEFAULT at launch. Also
    // degrades on payload presence (older exports have no etaAlignYears).
    const WINDOW_DEFAULT = true;   // surfaced: Window column on by default (#window=0 to hide)
    const _wp = new URLSearchParams((location.hash || "").replace(/^#/, "")).get("window");
    const windowOn = _wp != null ? _wp !== "0" : WINDOW_DEFAULT;
    const hasWindow = rows.some(r => (r.farm || {}).etaAlignYears != null);
    const showWindow = hasWindow && windowOn;
    // Current (2026) slate: dark-launched behind #now=1 (mirrors #window). Opt in
    // with #now=1; degrades on payload presence (older/degraded exports carry no
    // `current` block). When off, every branch below takes the existing 2027 path.
    const NOW_DEFAULT = false;
    const _np = new URLSearchParams((location.hash || "").replace(/^#/, "")).get("now");
    const nowFlag = _np != null ? _np !== "0" : NOW_DEFAULT;
    const hasNow = rows.some(r => r.current);
    const nowAvail = hasNow && nowFlag;
    // #now=1 should LAND on the Current slate the first time it's available this
    // session; a subsequent manual chip toggle (which sets teamModeTouched) then
    // sticks. The flag isn't persisted to URL (mirrors #window), so re-derive the
    // active slate every render and never trust a stale teamMode when the payload
    // is absent.
    if (nowAvail && !state.teamModeTouched) state.teamMode = "now";
    if (!nowAvail) state.teamMode = "proj";
    const nowMode = nowAvail && state.teamMode === "now";
    const curSeason = DATA.current_season || (DATA.first_season ? DATA.first_season - 1 : "");
    const pctStr = (p) => p == null ? EM_DASH : (p * 100).toFixed(1) + "%";
    const wlOf = (w, l) => `${Math.round(w)}-${Math.round(l)}`;
    // Window cell: an arrival-curve sparkline (share of farm surplus landing
    // each 2027-31 season + a later bucket) plus etaAlignYears, colored by
    // whether the farm lands inside the controlled-core window (<= 0 aligned).
    const windowCell = (r) => {
      const f = r.farm || {};
      const a = f.etaAlignYears;
      if (a == null) return EM_DASH;
      const by = Array.isArray(f.etaByYear) ? f.etaByYear : [];
      let spark = "";
      if (by.length) {
        const mx = Math.max(0.01, ...by);
        // Only the bar HEIGHT stays inline - it is the data. Everything else
        // (width, colour, radius) is presentation and lives on .proj-eta-bar.
        spark = `<span class="proj-eta-spark">${
          by.map((v, k) => {
            const yr = DATA.first_season + k;
            const lab = k === by.length - 1 ? `${yr}+` : `${yr}`;
            const h = Math.max(2, Math.round((v / mx) * 18));
            return `<span class="proj-eta-bar" title="${esc(`${lab}: ${Math.round(v * 100)}% of farm surplus`)}" style="height:${h}px;"></span>`;
          }).join("")
        }</span> `;
      }
      const col = a <= 0 ? "var(--up)" : a >= 1.5 ? "var(--down)" : "var(--text-primary)";
      const sign = a > 0 ? "+" : "";
      const tip = `Window alignment: the farm's surplus-weighted arrival (${f.etaMean != null ? f.etaMean : "?"}) vs the controlled-core WAR center (${f.coreCenter != null ? f.coreCenter : "?"}). ${a <= 0 ? "Farm lands inside the control window (aligned)." : "Farm arrives after the core leaks to free agency (gap)."} Bars = share of farm surplus by arrival season.`;
      return `<span class="proj-cell-inline" title="${esc(tip)}">${spark}<span class="proj-cell-num" style="color:${col};">${sign}${a.toFixed(1)}y</span></span>`;
    };
    // ---- Current (2026) cell-builders. All read r.current (the exporter's
    // nested block) and EM_DASH per-field when absent, so a partial payload
    // degrades cleanly. No math here beyond display formatting + bar widths. ----
    const currentCell = (r) => {
      const c = r.current; if (!c || c.record == null) return EM_DASH;
      const pc = c.actualPct != null ? (c.actualPct * 100).toFixed(1) + "%" : EM_DASH;
      const gb = c.gb != null ? (c.gb === 0 ? "div lead" : `${c.gb} GB`) : "";
      const tip = `Actual ${curSeason} record: ${c.record} (${pc})${gb ? " · " + gb : ""}${c.ilOut60 ? ` · ${c.ilOut60} on the 60-day IL` : ""}.`;
      return `<span class="proj-cell-nowrap" title="${esc(tip)}"><strong>${esc(c.record)}</strong> <span class="fa-sub">${pc}</span></span>`;
    };
    const pythagCell = (r) => {
      const c = r.current; if (!c || c.pythagPct == null) return EM_DASH;
      const delta = (c.actualPct != null) ? c.actualPct - c.pythagPct : null;
      const col = delta == null ? "var(--text-primary)"
        : delta >= 0.020 ? "var(--up)" : delta <= -0.020 ? "var(--down)" : "var(--text-primary)";
      const tip = `Pythagorean expectation ${(c.pythagPct * 100).toFixed(1)}% from run differential (exp 1.83).${delta != null ? ` Actual is ${delta >= 0 ? "over" : "under"}-performing by ${Math.abs(delta * 100).toFixed(1)} pts.` : ""}`;
      return `<span class="proj-cell-mono" title="${esc(tip)}" style="color:${col};">${(c.pythagPct * 100).toFixed(1)}%</span>`;
    };
    const blendCell = (r) => {
      const c = r.current; if (!c || c.curWins == null) return EM_DASH;
      const tip = `Projected full-season ${curSeason} record: ${wlOf(c.curWins, c.curLosses)} (${(c.curPct * 100).toFixed(1)}%). Bayesian blend of the roster-talent prior (${pctStr(c.talentPriorPct)}), actual record (${pctStr(c.actualPct)}), and Pythag (${pctStr(c.pythagPct)}); weights prior/actual/pythag = ${c.blendWeights ? [c.blendWeights.prior, c.blendWeights.actual, c.blendWeights.pythag].map(x => x.toFixed(2)).join("/") : "?"} at ${c.gamesPlayed} games played.`;
      return `<span class="proj-cell-nowrap" title="${esc(tip)}"><strong>${wlOf(c.curWins, c.curLosses)}</strong> <span class="fa-sub">${(c.curPct * 100).toFixed(1)}%</span></span>`;
    };
    const playoffCell = (r) => {
      const c = r.current; if (!c || c.playoffPct == null) return EM_DASH;
      const div = c.divisionPct || 0, wc = c.wildcardPct || 0, play = c.playoffPct || 0;
      const divW = Math.round(div * 100), wcW = Math.round(wc * 100);
      const missW = Math.max(0, 100 - divW - wcW);
      // Only the segment WIDTHS stay inline - they are the odds. The track box
      // and each segment's colour live on .proj-odds-* in the stylesheet.
      const bar = `<span class="proj-odds-bar">`
        + `<span class="proj-odds-div" style="width:${divW}%;"></span>`
        + `<span class="proj-odds-wc" style="width:${wcW}%;"></span>`
        + `<span class="proj-odds-miss" style="width:${missW}%;"></span></span>`;
      const proj = (c.projWinsP10 != null && c.projWinsP90 != null)
        ? ` Projected wins ${c.projWinsMean} (80% range ${c.projWinsP10}-${c.projWinsP90}).` : "";
      const tip = `Playoff odds ${(play * 100).toFixed(0)}% = division ${(div * 100).toFixed(0)}% + wildcard ${(wc * 100).toFixed(0)}% (Monte Carlo, ${DATA.mc_schedule_source === "balanced_fallback" ? "balanced-schedule estimate" : "live remaining schedule"}).${proj}`;
      return `<span class="proj-cell-inline" title="${esc(tip)}">${bar}<span class="proj-cell-num">${(play * 100).toFixed(0)}%</span></span>`;
    };
    const sosCell = (r) => {
      const c = r.current; if (!c || c.sos == null) return EM_DASH;
      const rk = c.sosRank != null ? `#${c.sosRank}` : "";
      const col = c.sos >= 0.520 ? "var(--down)" : c.sos <= 0.480 ? "var(--up)" : "var(--text-primary)";
      const tip = `Remaining strength of schedule (log5): avg opponent talent ${(c.sos * 100).toFixed(1)}% over ${c.remGames} unplayed games; rank ${rk} (1 = hardest). Expected ~${c.remWinExp} added wins the rest of the way.`;
      return `<span class="proj-cell-mono" title="${esc(tip)}" style="color:${col};">${(c.sos * 100).toFixed(1)}% <span class="fa-sub">${rk}</span></span>`;
    };
    // Core-control cell: a decline TREND of CONTROLLED WAR per season (the
    // cliff) + the WAR-weighted lock-up %. % colored up/down; the line is drawn
    // from r.byYear, verified on the shipped payload as
    // [{season, war, wins, losses, winsRaw, depthWar, n}, ...] - `war` is the
    // controlled-WAR series this cell has always plotted.
    //
    // The bar strip this replaced was the same data with no numbers on it: you
    // could see that the core declined but not from what to what. The endpoint
    // labels are the whole point of the fa.js chart being the best small viz in
    // the tree, and they are what the control cliff most needed.
    const controlCell = (r) => {
      const by = Array.isArray(r.byYear) ? r.byYear : [];
      const pct = r.lockedPct != null ? Math.round(r.lockedPct * 100) : null;
      if (!by.length && pct == null) return EM_DASH;
      const pctCol = pct == null ? "var(--text-secondary)"
        : pct >= 75 ? "var(--up)" : pct <= 45 ? "var(--down)" : "var(--text-primary)";
      const pctStr = pct == null ? EM_DASH : `${pct}%`;
      let spark = "";
      if (by.length) {
        spark = miniTrendSVG(
          by.filter(s => s && Number.isFinite(Number(s.war)))
            .map(s => ({ v: s.war, t: `${s.season}: ${fmtWar(s.war)} controlled WAR` })),
          { color: "var(--accent-cyan)", fmt: v => fmtWar(v),
            aria: `Controlled WAR by season, ${by[0].season} to ${by[by.length - 1].season}` });
        if (spark) spark += " ";
      }
      const tip = (r.ctrlWar5y != null && r.fullWar5y != null && by.length)
        ? `Cost-controlled core: ${pctStr} of projected ${by[0].season}-${by[by.length - 1].season} WAR is locked up (${r.ctrlWar5y} of ${r.fullWar5y} WAR-seasons under team control). The line is controlled WAR per season, labelled at both ends; the cliff is players reaching free agency.`
        : "Cost-controlled core lock-up";
      return `<span class="proj-ctrl" title="${esc(tip)}">${spark}<span class="proj-ctrl-pct" style="color:${pctCol};">${pctStr}</span></span>`;
    };
    // Click-sortable columns. `natural` = first-click direction; clicking the
    // same header again flips it (state.teamDir). Nulls always sink. Default
    // (teamSort null) preserves the export's roster-WAR ranking.
    const TEAM_SORTS = {
      team:      { get: r => r.team || "", text: true, natural: "asc" },
      war:       { get: r => r.war, natural: "desc" },
      wins:      { get: r => r.wins, natural: "desc" },
      control:   { get: r => r.lockedPct, natural: "desc" },
      window:    { get: r => (r.farm || {}).etaAlignYears, natural: "asc" },
      farm:      { get: r => (r.farm || {}).farmRank, natural: "asc" },
      surplus:   { get: r => (r.farm || {}).farmSurplusMM, natural: "desc" },
      prospect:  { get: r => ((r.farm || {}).topProspect || {}).fv, natural: "desc" },
      projected: { get: r => ((r.top || [])[0] || {}).war, natural: "desc" },
      // Current (2026) columns - only active in now-mode; additive, no collision.
      nowPct:    { get: r => (r.current || {}).actualPct, natural: "desc" },
      pythag:    { get: r => (r.current || {}).pythagPct, natural: "desc" },
      blend:     { get: r => (r.current || {}).curPct, natural: "desc" },
      playoff:   { get: r => (r.current || {}).playoffPct, natural: "desc" },
      sos:       { get: r => (r.current || {}).sos, natural: "desc" },
    };
    const _sortAsc = (key) => {
      const col = TEAM_SORTS[key];
      const naturalAsc = col.natural === "asc";
      return (state.teamDir === -1) ? !naturalAsc : naturalAsc;
    };
    let viewRows = rows.slice();
    if (state.teamSort && TEAM_SORTS[state.teamSort]) {
      const col = TEAM_SORTS[state.teamSort];
      const asc = _sortAsc(state.teamSort);
      viewRows.sort((a, b) => {
        let av = col.get(a), bv = col.get(b);
        if (col.text) {
          const r = String(av || "").localeCompare(String(bv || ""));
          return asc ? r : -r;
        }
        av = (av == null || isNaN(Number(av))) ? null : Number(av);
        bv = (bv == null || isNaN(Number(bv))) ? null : Number(bv);
        if (av == null && bv == null) return 0;
        if (av == null) return 1;
        if (bv == null) return -1;
        return asc ? (av - bv) : (bv - av);
      });
    }
    const body = viewRows.map((r, i) => {
      const f = r.farm || {};
      const farmCell = f.farmRank != null
        ? `<a href="/prospx/#farm-org=${encodeURIComponent(r.team)}" title="PROSPX farm system detail">#${f.farmRank}</a> <span class="fa-sub">${f.farmScore != null ? Math.round(f.farmScore) : ""}</span>`
        : EM_DASH;
      const surCell = f.farmSurplusMM != null
        ? `<span class="${f.farmSurplusMM >= 0 ? "proj-pos" : "proj-neg"}" title="Net control-window NPV over the org's active prospect pool">$${Math.round(f.farmSurplusMM)}M</span>`
        : EM_DASH;
      const topCell = f.topProspect
        ? `<a class="fa-player-link" href="/prospx/#player=${encodeURIComponent(f.topProspect.key || "")}">${esc(f.topProspect.name)}</a> <span class="fa-sub">FV ${esc(String(f.topProspect.fv || "?"))}</span>`
        : EM_DASH;
      const openCell = `<a href="/prospx/#farm-org=${encodeURIComponent(r.team)}">farm</a> · <a href="/prospx/#farm-org=${encodeURIComponent(r.team)}&ftab=tendencies" title="Open the Org Tendencies tab">tendencies</a> · <a href="/fa/#view=fits&team=${encodeURIComponent(r.team)}">FA fits</a> · <a href="#team=${encodeURIComponent(r.team)}" data-team-filter="${esc(r.team)}">roster</a>`;
      const w = Math.round(r.wins);
      const wl = `${w}-${162 - w}`;
      const wlTip = r.depthWar != null
        ? `Roster WAR + ${r.depthWar} depth-allowance WAR over the 47.7 replacement baseline (league recentered to 2,430 total wins${r.winsRaw != null ? `; raw roster-only read ${Math.round(r.winsRaw)} wins` : ""})`
        : `Roster WAR over the 47.7 replacement baseline`;
      if (nowMode) {
        // Current (2026) slate: actual record / Pythag / blended projection /
        // playoff odds / remaining SOS. Team + rank columns are shared.
        return `<tr>
      <td>${i + 1}</td>
      <td class="proj-player">${teamLogo(r.team)}<strong>${esc(r.team)}</strong></td>
      <td>${currentCell(r)}</td>
      <td>${pythagCell(r)}</td>
      <td>${blendCell(r)}</td>
      <td>${playoffCell(r)}</td>
      <td>${sosCell(r)}</td>
    </tr>`;
      }
      return `<tr>
      <td>${i + 1}</td>
      <td class="proj-player">${teamLogo(r.team)}<strong>${esc(r.team)}</strong></td>
      <td class="proj-war${warClass(r.war / 8)}">${r.war.toFixed(1)}</td>
      <td title="${esc(wlTip)}"><strong>${wl}</strong></td>
      ${hasControl ? `<td>${controlCell(r)}</td>` : ""}
      ${showWindow ? `<td>${windowCell(r)}</td>` : ""}
      ${hasFarm ? `<td>${farmCell}</td><td>${surCell}</td><td>${topCell}</td>` : ""}
      <td class="fa-sub">${(r.top || []).map(p => `<a class="fa-player-link" href="#player=${encodeURIComponent(p.key)}">${esc(p.name)}</a> ${p.war.toFixed(1)}`).join(" · ")}</td>
      ${hasFarm ? `<td class="fa-sub proj-cell-nowrap">${openCell}</td>` : ""}
    </tr>`;
    }).join("");
    const note = nowMode
      ? `Current (${curSeason}) slate <span class="eephus-beta" title="Newly launched; blend + odds may shift">β beta</span>: a Bayesian blend of the roster-talent prior, actual record, and Pythagorean expectation (RS/RA). Prior acts as ~40 pseudo-games, so it leads early and fades toward the in-season signals as the season progresses. Playoff odds are a ${DATA.mc_schedule_source === "balanced_fallback" ? "Monte Carlo over a balanced-schedule ESTIMATE (live schedule unavailable)" : "Monte Carlo over the live remaining schedule"}; SOS is the log5 average opponent talent over unplayed games (rank 1 = hardest). This view is additive and does not change the projection board.`
      : `Current-season (${DATA.first_season}) roster bWAR -> projected wins at the 47.7 replacement baseline (forward-gated against actual standings).${hasControl ? ` Core control measures organizational strength for the FUTURE: the WAR-weighted share of each org's projected 2027-${DATA.first_season + (DATA.horizon || 5) - 1} production that is cost-controlled (under contract or club control) - 100% means the whole core is locked through the horizon, a low % means it leaks to free agency. The sparkline is controlled WAR per season; the drop-off is the control cliff.` : ""}${hasFarm ? " Farm rank, surplus, and top prospect join from the PROSPX org models." : ""}`;
    // Sortable header: click to sort by it, click again to flip direction.
    // The active column shows a ▲/▼ arrow reflecting the effective direction.
    const _arrow = (key) => state.teamSort === key
      ? ` <span class="proj-sort-arrow">${_sortAsc(key) ? "▲" : "▼"}</span>` : "";
    const sth = (key, label, title) =>
      `<th class="proj-sortable" data-team-sort="${key}"${title ? ` title="${esc(title)}"` : ""}>${label}${_arrow(key)}</th>`;
    // Mode sub-chips (only when the current-season payload is available + opted in).
    const modeChips = nowAvail
      ? `<div class="proj-mode-chips">
        <button class="chip${!nowMode ? " active" : ""}" data-team-mode="proj">Projected (${DATA.first_season})</button>
        <button class="chip${nowMode ? " active" : ""}" data-team-mode="now">Current (${curSeason})</button></div>`
      : "";
    const header = nowMode
      ? `<thead><tr><th>#</th>${sth("team", "Team")}${sth("nowPct", "Record", `Actual ${curSeason} record + win%`)}${sth("pythag", "Pythag", "Pythagorean win% from run differential (exp 1.83)")}${sth("blend", "Proj W-L", "Bayesian blend of talent prior + actual + Pythag -> projected full-season record")}${sth("playoff", "Playoff odds", "Monte-Carlo division/wildcard/playoff probability")}${sth("sos", "Rem SOS", "Remaining strength of schedule via log5 (rank 1 = hardest)")}</tr></thead>`
      : `<thead><tr><th>#</th>${sth("team", "Team")}${sth("war", "Roster WAR")}${sth("wins", "Proj W-L", "Projected record, league-recentered (depth allowance over the rostered universe)")}${hasControl ? sth("control", "Core control", `Cost-controlled core: WAR-weighted share of projected ${DATA.first_season}-${DATA.first_season + (DATA.horizon || 5) - 1} WAR under team control (sparkline = controlled WAR per season)`) : ""}${showWindow ? sth("window", "Window", `System Duration: farm surplus-weighted arrival vs the controlled-core window. Negative = the farm lands while the core is still under control (aligned); positive = it arrives after the core leaks. Bars = share of farm surplus by arrival season.`) : ""}${hasFarm ? `${sth("farm", "Farm", "PROSPX farm-system rank + grade score")}${sth("surplus", "Farm surplus", "Net control-window NPV over the org's active prospect pool")}${sth("prospect", "Top prospect", "Sort by top prospect FV")}` : ""}${sth("projected", "Top projected", "Sort by the org's top projected player WAR")}${hasFarm ? "<th>Open</th>" : ""}</tr></thead>`;
    root.innerHTML = `${modeChips}<div class="fa-note proj-teams-note">${note}</div>
      <table class="detail-table proj-table">
      ${header}
      <tbody>${body}</tbody></table>`;
    root.querySelectorAll("[data-team-sort]").forEach(h => h.onclick = () => {
      const k = h.dataset.teamSort;
      if (state.teamSort === k) state.teamDir = state.teamDir === -1 ? 1 : -1;
      else { state.teamSort = k; state.teamDir = 1; }
      renderTeams();
    });
    root.querySelectorAll("[data-team-mode]").forEach(b => b.onclick = () => {
      const m = b.dataset.teamMode;
      if (m === state.teamMode) return;
      // Switching slates: the two modes have disjoint sortable columns, so clear
      // any active sort to avoid a stale key pointing at a now-hidden column.
      // teamModeTouched pins the user's choice over the #now=1 auto-land default.
      state.teamMode = m; state.teamModeTouched = true;
      state.teamSort = null; state.teamDir = 1;
      renderTeams();
    });
    root.querySelectorAll("[data-team-filter]").forEach(a => a.onclick = (ev) => {
      ev.preventDefault();
      state.view = "players"; state.team = a.dataset.teamFilter;
      syncToURL(); render();
    });
    if (window.EEPHUS_GL) window.EEPHUS_GL.wire(root);
  }

  // ===========================================================================
  // Model Accountability (#view=accountability) - the projection models'
  // owner-committed verdicts + methodology (data/model_registry.json) with the
  // held-out backtest receipts read verbatim from the committed eval artifacts
  // (proj_export._accountability_block). Pure surfacing: the audit ledger is the
  // single source of truth, nothing is recomputed here. The numbers shown match
  // the committed *_eval.json files byte-for-byte.
  // ===========================================================================
  const VERDICT_META = {
    validated:   { label: "Validated",   col: "var(--accent-green)" },
    provisional: { label: "Provisional", col: "var(--accent-gold)" },
    unvalidated: { label: "Unvalidated", col: "var(--down)" },
    deprecated:  { label: "Deprecated",  col: "var(--text-tertiary)" },
  };
  const VERDICT_DESC = {
    validated: "forward-chained backtest beats the baseline",
    provisional: "measured, but partially (short window or descriptive)",
    unvalidated: "predictive claim with no measurement yet",
    deprecated: "failed validation, retired",
  };
  function verdictBadge(v) {
    const m = VERDICT_META[v] || { label: v || "?", col: "var(--text-tertiary)" };
    // Only `background` stays inline: it is a computed VALUE (the verdict's own
    // colour). Shape, type and the on-badge text colour live on .proj-verdict.
    return `<span class="proj-verdict" style="background:${m.col};">${esc(m.label)}</span>`;
  }
  function _num(v, d) {
    return v == null || !Number.isFinite(Number(v)) ? EM_DASH : Number(v).toFixed(d == null ? 2 : d);
  }
  function _signed(v, d) {
    if (v == null || !Number.isFinite(Number(v))) return EM_DASH;
    const n = Number(v);
    return (n >= 0 ? "+" : "") + n.toFixed(d == null ? 2 : d);
  }
  function _pct0(v) {
    return v == null || !Number.isFinite(Number(v)) ? EM_DASH : (Number(v) * 100).toFixed(0) + "%";
  }

  // Team win totals - the retro backtest per season (cohort-recentered roll-up
  // vs the prior-wins carry-forward baseline) + the player-level pooled read,
  // the ship gate, and the still-pending forward gate.
  function teamWinsTable(tw) {
    if (!tw || !(tw.per_season || []).length) return "";
    const rows = tw.per_season.map(s => `<tr>
      <td>${s.season}${s.is_holdout ? ` <span class="proj-tag" title="Held out of the cohort-intercept fit" data-gl="holdout">holdout</span>` : ""}</td>
      <td>${s.n_assigned_players ?? EM_DASH}</td>
      <td class="proj-acct-key">${_num(s.mae)}</td>
      <td>${_num(s.r)}</td>
      <td class="fa-sub">${_num(s.baseline_mae)}</td>
    </tr>`).join("");
    const fg = tw.forward_gate || {};
    const pooled = tw.player_pooled || {};
    const sd = tw.ship_decision || {};
    const hm = sd.holdout_mae || {};
    return `<table class="detail-table proj-table proj-acct-table">
      <thead><tr><th>Season</th><th title="Players assigned to their actual season team">Roster n</th>
        <th title="Mean absolute error in projected team wins, cohort-recentered roll-up (lower is better)"><span data-gl="mae">MAE</span> (wins)</th>
        <th title="Correlation of projected vs actual wins">r</th>
        <th title="Prior-season wins carry-forward baseline MAE">Baseline</th></tr></thead>
      <tbody>${rows}</tbody></table>
      <div class="fa-sub proj-acct-foot">Player-level engine pooled bias ${_signed(pooled.bias_act_minus_pred)} WAR, MAE ${_num(pooled.mae)} (n=${pooled.n ?? "?"}).${sd.holdout_season ? ` Ship gate on the ${sd.holdout_season} holdout: cohort-recentered ${_num(hm.cohort_recentered)} vs prior-wins baseline ${_num(hm.baseline_prior_wins)} - ${sd.challenger_wins ? "shipped" : "baseline retained"} (published either way).` : ""}</div>
      <div class="fa-note proj-acct-foot"><span data-gl="forward_gate">Forward gate</span>: ${esc(fg.status || "pending")} - ${esc(fg.scope || "first season only")}; first scoreable ${esc(fg.first_scoreable || "end of the 2027 season")}. ${esc(fg.metric || "")}</div>`;
  }

  // Veteran WAR paths - the touched-once 2022-24 holdout, champion vs baseline
  // per horizon (MAE + bias + P10-P90 coverage). Holdout labels mature only
  // through h4, so the table runs as deep as the artifact reports.
  function vetHorizonsTable(vh) {
    const ch = (vh && vh.champion && vh.champion.horizons) || [];
    if (!ch.length) return "";
    const bl = (vh.baseline && vh.baseline.horizons) || [];
    const blByH = {}; bl.forEach(r => { blByH[r.h] = r; });
    const rows = ch.map(r => {
      const b = blByH[r.h] || {};
      return `<tr>
        <td>h${r.h}</td>
        <td class="proj-acct-key">${_num(r.mae)}</td>
        <td class="fa-sub">${b.mae != null ? _num(b.mae) : EM_DASH}</td>
        <td>${_signed(r.bias)}</td>
        <td>${_pct0(r.coverage)}</td>
        <td class="fa-sub">${b.coverage != null ? _pct0(b.coverage) : EM_DASH}</td>
      </tr>`;
    }).join("");
    return `<table class="detail-table proj-table proj-acct-table">
      <thead><tr><th title="Projection horizon, seasons ahead">Horizon</th>
        <th title="Champion mean absolute WAR error (lower is better)"><span data-gl="mae">MAE</span></th>
        <th title="Baseline MAE" class="fa-sub">Baseline</th>
        <th title="Mean error, actual minus predicted">Bias</th>
        <th title="Share of actuals inside the P10-P90 band (target ~80%)"><span data-gl="p10_p90_bands">Coverage</span></th>
        <th title="Baseline coverage" class="fa-sub">Baseline</th></tr></thead>
      <tbody>${rows}</tbody></table>
      <div class="fa-sub proj-acct-foot">${esc(vh.frame || "")} Champion ${esc((vh.champion || {}).model || "")} vs prior baseline ${esc((vh.baseline || {}).model || "")}.</div>`;
  }

  // Prospect post-ETA paths - forward-chained debut cohorts: the FV-only
  // scouting-consensus champion vs the MiLB-stats challenger that lost.
  function prospectPathsTable(pp) {
    if (!pp || !pp.champion) return "";
    const c = pp.champion, ch = pp.challenger || {};
    return `<table class="detail-table proj-table proj-acct-table">
      <thead><tr><th>Model</th><th>n</th><th><span data-gl="mae">MAE</span> (WAR)</th><th title="Rank correlation vs realized first-3y WAR (the ship metric)">Spearman</th></tr></thead>
      <tbody>
        <tr><td>${esc(c.label || "champion")} <span class="proj-tag">champion</span></td><td>${c.n ?? EM_DASH}</td><td>${_num(c.mae)}</td><td class="proj-acct-key">${_num(c.spearman, 3)}</td></tr>
        <tr><td class="fa-sub">${esc(ch.label || "challenger")}</td><td>${ch.n ?? EM_DASH}</td><td>${_num(ch.mae)}</td><td>${_num(ch.spearman, 3)}</td></tr>
      </tbody></table>
      <div class="fa-sub proj-acct-foot">Forward-chained debut cohorts ${esc((pp.scored_years || []).join(", "))}. The scouting-consensus FV model ranks better (higher Spearman); stat-line challengers lost the pre-registered dual gate and are committed as losses.</div>`;
  }

  // Board spec for the Generate GFX modal on the Model Accountability view:
  // the owner-committed model-verdict ledger (model, surface, metric, verdict
  // badge) straight from data/model_registry.json - the same rows the cards
  // below render. Verdict colour: validated green, provisional muted,
  // deprecated/unvalidated red (a non-validated warning state).
  function _accountabilityBoardSpec(models) {
    const vcol = { validated: "green", provisional: "muted", deprecated: "red", unvalidated: "red" };
    const rows = models.map(m => {
      const vl = VERDICT_META[m.verdict] ? VERDICT_META[m.verdict].label : (m.verdict || "?");
      return { cells: [
        { t: m.label || m.model_id || "?" },
        { t: m.surface || EM_DASH, c: "muted" },
        { t: m.metric || EM_DASH },
        { t: vl, c: vcol[m.verdict] || "muted", bold: true },
      ] };
    });
    const acct = DATA.accountability || {};
    return {
      kind: "board", module: "MLB Projections", accentToken: "--accent-cyan",
      title: "MLB Projections · Model Accountability",
      subtitle: `${models.length} projection models graded against held-out history`
        + (acct.registry_version ? ` · registry ${acct.registry_version}` : ""),
      url: "eephus.io/projections", filenameBase: "eephus-projections-accountability",
      caption: "Owner-committed verdicts · each model beats a baseline on a forward-chained backtest before it ships",
      board: { defaultCount: 25, counts: [10, 25, 50], legend: "verdict per model_registry", columns: [
        { label: "Model", frac: 0.28 },
        { label: "Surface", frac: 0.28 },
        { label: "Metric", frac: 0.30, wideOnly: true },
        { label: "Verdict", frac: 0.14 },
      ], rows },
    };
  }

  function renderAccountability() {
    const root = document.getElementById("proj-rows");
    const bar = document.getElementById("proj-filters");
    const banner = document.getElementById("proj-banner");
    const acct = DATA.accountability || {};
    bar.innerHTML = viewChips("accountability");
    bar.querySelectorAll("[data-pv]").forEach(b => b.onclick = () => {
      state.view = b.dataset.pv; syncToURL(); render();
    });
    if (banner) {
      const acctGfxChip = ((acct.models || []).length && window.EEPHUS_GFX)
        ? ` &middot; ${window.EEPHUS_GFX.chipHTML("proj-acct-gfx", "Generate GFX")}` : "";
      banner.innerHTML = `<div class="fa-note fa-sources">
        How these projections are validated: held-out <span data-gl="backtest">backtests</span>, owner-committed model <span data-gl="model_verdict">verdicts</span>, and a note on what is not yet scoreable.
        ${acct.registry_version ? `&middot; model registry ${esc(String(acct.registry_version))}` : ""}${acct.generated_at ? ` &middot; as of ${esc(String(acct.generated_at))}` : ""}${acctGfxChip}</div>`;
    }
    const models = acct.models || [];
    if (!models.length) {
      root.innerHTML = `<div class="state-message">This view is temporarily unavailable. Check back shortly.</div>`;
      if (window.EEPHUS_GL && banner) window.EEPHUS_GL.wire(banner);
      return;
    }
    const bt = acct.backtests || {};
    const tableFor = (art) => {
      if (art === "data/team_outlook_eval.json") return teamWinsTable(bt[art]);
      if (art === "data/proj_horizon_eval.json") return vetHorizonsTable(bt[art]);
      if (art === "data/prospect_path_eval.json") return prospectPathsTable(bt[art]);
      return "";
    };
    const legend = (acct.verdict_enum || []).map(v =>
      VERDICT_META[v] ? `<span class="proj-acct-legend-item">${verdictBadge(v)} <span class="fa-sub">${esc(VERDICT_DESC[v] || "")}</span></span>` : "").join("");
    const glHref = `/glossary/#cat=${encodeURIComponent("Platform & Methodology")}`;
    const cards = models.map(m => {
      const fresh = m.last_checked
        ? `last checked ${esc(String(m.last_checked))}${m.artifact_age_days != null ? ` &middot; artifact ${m.artifact_age_days}d old` : ""}${m.stale ? ` &middot; <span class="proj-neg">stale</span>` : ""}`
        : "";
      return `<div class="mlbp-section proj-acct-card">
        <div class="proj-acct-head">
          <span class="mlbp-section-title">${esc(m.label)}</span>${verdictBadge(m.verdict)}
        </div>
        <div class="fa-sub proj-acct-predicts">${esc(m.predicts || "")}</div>
        <div class="proj-acct-meta">
          <strong>Champion</strong> ${esc(m.champion || "?")}<br>
          <strong>Baseline</strong> <span class="fa-sub">${esc(m.baseline || "?")}</span><br>
          <strong>Metric</strong> <span class="fa-sub">${esc(m.metric || "?")}</span>
        </div>
        ${tableFor(m.eval_artifact)}
        ${m.notes ? `<details class="proj-acct-notes"><summary class="fa-sub">Methodology and disclosures</summary><div class="fa-note">${esc(m.notes)}</div></details>` : ""}
        ${fresh ? `<div class="fa-sub proj-acct-fresh">${fresh} &middot; <a href="${glHref}">methodology glossary</a></div>` : ""}
      </div>`;
    }).join("");
    root.innerHTML = `<div class="mlbp-page">
      <div class="fa-note proj-block-note">Every projection on this site is graded against held-out history before it ships. Each model below shows its champion, the baseline it beat, the metric, the measured result, and a note on what is not yet gateable. Verdicts come from the platform's model registry, refreshed monthly.</div>
      <div class="proj-acct-legend">${legend}</div>
      ${cards}</div>`;
    const agfx = document.getElementById("proj-acct-gfx");
    if (agfx) agfx.onclick = () => {
      if (window.EEPHUS_GFX && models.length) window.EEPHUS_GFX.open(_accountabilityBoardSpec(models));
    };
    if (window.EEPHUS_GL) { if (banner) window.EEPHUS_GL.wire(banner); window.EEPHUS_GL.wire(root); }
  }

  function sortHead(label, key, title) {
    const active = state.sort === key;
    return `<th class="proj-sort${active ? " is-sorted" : ""}" data-psort="${key}" title="${esc(title || "Click to sort")}">${label}${active ? (state.dir < 0 ? " ▾" : " ▴") : ""}</th>`;
  }

  function renderTable() {
    const root = document.getElementById("proj-rows");
    const first = DATA.first_season;
    const list = sortRows(rows());
    const seasons = Array.from({ length: DATA.horizon }, (_, t) => first + t);
    const body = list.slice(0, state.limit).map((m, i) => {
      // Season cells, emitted as tape chips. Each carries its own season label,
      // which is what lets the strip live in row 2 without a separate header
      // row to align against.
      const cellChips = seasons.map((s, t) => {
        const chip = (cls, val, title) =>
          `<div class="mlb-chip ${cls}"${title ? ` title="${title}"` : ""}><b>${s}</b>${val}</div>`;
        if (state.cells !== "war") {
          const v = rateAt(m, t);
          if (v == null) {
            const milb = m.src === "prospect" && s < m.eta;
            return chip("proj-dim", milb ? "MiLB" : EM_DASH);
          }
          const mm = RATE_META[state.cells];
          return chip("proj-war" + rateClass(v), mm.fmt(v),
            `${s}: ${esc(mm.tip)}. Rate line = the year-1 Marcel components walked along the engine's aging curves (display path; WAR and pricing are unaffected).`);
        }
        const w = warAt(m, t);
        if (w == null) {
          const milb = m.src === "prospect" && s < m.eta;
          return chip("proj-dim", milb ? "MiLB" : EM_DASH);
        }
        const lo = bandAt(m, t, "lo"), hi = bandAt(m, t, "hi");
        return chip("proj-war" + warClass(w), fmtWar(w),
          `${s}: ${fmtWar(w)} bWAR (playing-time-held / if-healthy path)${lo != null ? ` &middot; floor ${fmtWar(lo)} / ceiling ${fmtWar(hi)} (P10-P90 outcomes)` : ""}`);
      }).join("");
      // For prospects the per-season cells render only the fixed calendar window,
      // which can drop ETA-shifted prime seasons; sum the SHOWN cells so the Total
      // column agrees with what is visible. Vets keep their full warTotalPTH.
      const totV = m.src === "prospect"
        ? seasons.map((s, t) => warAt(m, t)).filter(v => v != null).reduce((a, b) => a + b, 0)
        : (m.warTotalPTH ?? m.warTotal);
      // Total-WAR P10-P90 band dropped (F-01): the band summed per-year
      // quantiles and the per-year marginals undercover realized totals, so it
      // was miscalibrated. Point estimate stays; per-year bands are unaffected.
      const tot = `${fmtWar(totV)}`;
      const cs = contractStatus(m);
      // Contract status moved OUT of row 1 into the tape (2026-07-31): it is a
      // categorical chip rather than a number, and its row-1 header sorted by
      // AGE, which is the kind of mismatch nobody discovers except by testing a
      // sort they did not ask for. AAV came out of it into a column of its own,
      // which is also what finally made AAV sortable at all.
      const ctChip = `<div class="mlb-chip mlb-chip-ct" title="${esc(cs.tip)}"><b>contract</b><span class="proj-ct ${cs.cls}">${esc(cs.label)}</span></div>`;
      const aavCell = m.aav != null ? money(m.aav) : EM_DASH;
      const peakChip = m.warPeak != null
        ? `<div class="mlb-chip" title="Prime projection: roughly this per year at peak age on the talent path. Surplus prices the attrition-discounted expected value, not this."><b>peak WAR</b>${fmtWar(m.warPeak)}</div>`
        : "";
      const _sv = surOf(m);
      const _surTitle = m.src === "prospect"
        ? "Platform prospect surplus value (control window, service-time aware, $/WAR-escalated)"
        : (m.surRos != null && m.surNpv == null
            ? `Rest-of-season control only: ${Math.round((m.rosFrac || 0) * 100)}% of ${DATA.first_season - 1} still to play, priced on the prorated projection minus the prorated salary`
            : (m.surRos != null
                ? "Balance of the season in progress plus the NPV of (convex production value − salary) over salary-known seasons"
                : "NPV of (convex production value − salary) over salary-known seasons"));
      const sur = _sv != null
        ? `<span class="${_sv >= 0 ? "proj-pos" : "proj-neg"}" title="${_surTitle}">${money(_sv)}</span>`
        : EM_DASH;
      const link = m.src === "prospect"
        ? `<a class="fa-player-link" href="/prospx/#player=${encodeURIComponent(m.key)}"><strong>${esc(m.name)}</strong></a>`
        : `<a class="fa-player-link" href="#player=${encodeURIComponent(m.key)}"><strong>${esc(m.name)}</strong></a>`;
      const inCmp = state.cmp.includes(m.key);
      // The whole appearance (including the picked-vs-unpicked colours) is on
      // .proj-cmp-btn / .proj-cmp-btn.active - the class already encoded the
      // state, so the inline copy of it was duplicated truth, not a value.
      const cmpBtn = `<button class="proj-cmp-btn${inCmp ? " active" : ""}" data-cmp-key="${esc(m.key)}" type="button" title="${inCmp ? "Remove from compare" : "Compare head-to-head (pick two players)"}">⇄</button>`;
      // PROSPX-pattern card (Lane B, 2026-07-30). Row 1 carries identity and the
      // headline numbers; row 2 is a full-width tape of the season-by-season
      // projection. The old markup put six elements into a single ellipsized
      // 320px table cell, which is what made the board feel cramped: the fix is
      // to give the seasons their own band rather than to keep widening a row.
      const seasonTape = `<div class="mlb-tape"><div class="mlb-tape-inner">${cellChips}${peakChip}${ctChip}</div></div>`;
      const cardHref = m.src === "prospect"
        ? `/prospx/#player=${encodeURIComponent(m.key)}`
        : `#player=${encodeURIComponent(m.key)}`;
      return `<div class="mlb-card proj-card" tabindex="0" role="button"
          data-card-href="${esc(cardHref)}"${m.orgColor ? ` style="--org-color:${esc(m.orgColor)}"` : ""}>
        <span class="mlb-rank">${i + 1}</span>
        <div class="proj-id">
          <span class="mlb-name">${teamLogo(m.team)}${link}</span>
          <span class="mlb-sub">${esc(m.pos || "")}${m.team ? "" : " &middot; FA"}${tagFor(m)}<span class="proj-fa-slot" data-fa-key="${esc(m.key)}"></span>${cmpBtn}</span>
        </div>
        <span class="mlb-metric" title="Projected bWAR over the window on the playing-time-held (if-healthy) path. Peak-age rate is in the tape.">
          <span class="mlb-metric-label">${DATA.horizon}y WAR</span>${tot}</span>
        <span class="mlb-metric" title="Average annual value of the guaranteed contract on file. Prospects and players without a multi-year deal carry none."><span class="mlb-metric-label">AAV</span>${aavCell}</span>
        <span class="mlb-metric" title="Player age as carried on the projection row (the aging curves run forward from it)"><span class="mlb-metric-label">Age</span>${m.age != null ? Math.floor(m.age) : "?"}</span>
        <span class="mlb-metric"><span class="mlb-metric-label">Surplus</span>${sur}</span>
        ${seasonTape}
      </div>`;
    }).join("");
    const _wm = projWarMap(list);
    // font-size lives in CSS, not inline: an inline declaration outranks every
    // stylesheet, so the 11px here survived the coarse-pointer rule that lifts
    // fields to 16px and kept iOS zooming the page on focus. .proj-select
    // already carries the compact desktop size.
    const _axSel = (id, cur) => `<select id="${id}" class="proj-select proj-select-ax">
      ${Object.entries(SCATTER_AXES).map(([k, ax]) => `<option value="${k}"${cur === k ? " selected" : ""}>${esc(ax.label)}</option>`).join("")}</select>`;
    const _ay = (SCATTER_AXES[state.sy] || SCATTER_AXES.warY1).label;
    const _ax2 = (SCATTER_AXES[state.sx] || SCATTER_AXES.age).label;
    // Compact legend for the scatter's color encoding (contract status) -
    // swatches share CONTRACT_DOT_COLORS with the dots; labels mirror the
    // Contract filter chips. var() tokens keep it correct in both themes.
    // Only the swatch BACKGROUND stays inline - it is a computed value out of
    // CONTRACT_DOT_COLORS, the same map the dots read. Everything else is
    // .proj-warmap-legend / .proj-legend-item / .proj-legend-dot.
    const warMapLegend = `<div class="proj-warmap-legend">
        <span class="proj-warmap-legend-lede">dot color = contract status</span>
        ${[["signed", "Signed"], ["expiring", "Expiring"], ["controlled", "Cost-ctrl / unsigned"], ["prospect", "Prospect"]].map(([k, l]) =>
          `<span class="proj-legend-item"><span class="proj-legend-dot" style="background:${CONTRACT_DOT_COLORS[k]};" aria-hidden="true"></span>${l}</span>`).join("")}
      </div>`;
    const warMap = _wm ? `<details class="proj-warmap"><summary>Scatter &middot; ${esc(_ay)} vs ${esc(_ax2)} (current filters &middot; pick any axes)</summary>
      <div class="proj-warmap-axes">
        <span>Y</span>${_axSel("proj-sy", state.sy)}<span>X</span>${_axSel("proj-sx", state.sx)}
      </div>
      ${warMapLegend}
      <div class="proj-warmap-wrap" data-export-chart data-export-title="${esc(_ay)} vs ${esc(_ax2)}">${_wm}</div></details>` : "";
    // Right information rail for the Players view. Rebuilt inside renderTable so
    // the leaders and pool-supply modules track the CURRENT filtered/sorted
    // rows. View switching lives in the top filter-bar chips, so this rail is a
    // pure read-out: scope/freshness, the WAR and surplus leaders, pool supply.
    function projBoardSidebar(curr) {
      const stampMod = `<div class="fa-rail-mod"><div class="fa-rail-head" title="Data freshness and scope">Scope</div>
        ${DATA.generated_at ? `<div class="fa-rail-row"><span>data as of</span><span class="fa-rail-num">${esc(String(DATA.generated_at))}</span></div>` : ""}
        <div class="fa-rail-row"><span>veterans</span><span class="fa-rail-num">${DATA.n_vets}</span></div>
        <div class="fa-rail-row"><span>prospects</span><span class="fa-rail-num">${DATA.n_prospects}</span></div>
        <div class="fa-rail-row"><span data-gl="winter_dpw">$/WAR</span><span class="fa-rail-num">${money(DATA.dpw_usd)}</span></div></div>`;
      const warTot = m => warShown(m) ?? -99;   // same windowed 5yr total the board sorts + shows
      const topWar = curr.slice().sort((a, b) => warTot(b) - warTot(a)).slice(0, 6);
      const warRow = m => `<div class="fa-rail-row"><a class="fa-player-link" href="${m.src === "prospect" ? `/prospx/#player=${encodeURIComponent(m.key)}` : `#player=${encodeURIComponent(m.key)}`}">${esc(m.name)}</a><span class="fa-rail-num">${fmtWar(warTot(m))}</span></div>`;
      const warMod = `<div class="fa-rail-mod"><div class="fa-rail-head" title="Top ${DATA.horizon}-year projected bWAR among the current filters (if-healthy path)">Top projected WAR</div>
        ${topWar.map(warRow).join("")}</div>`;
      const surList = curr.filter(m => surOf(m) != null).sort((a, b) => (surOf(b) || 0) - (surOf(a) || 0)).slice(0, 6);
      const surRow = m => `<div class="fa-rail-row"><a class="fa-player-link" href="${m.src === "prospect" ? `/prospx/#player=${encodeURIComponent(m.key)}` : `#player=${encodeURIComponent(m.key)}`}">${esc(m.name)}</a><span class="fa-rail-num ${surOf(m) >= 0 ? "proj-pos" : "proj-neg"}">${money(surOf(m))}</span></div>`;
      const surMod = surList.length ? `<div class="fa-rail-mod"><div class="fa-rail-head" title="Largest surplus NPV among the current filters - value above salary where a real contract exists">Best surplus</div>
        ${surList.map(surRow).join("")}</div>` : "";
      const groups = {};
      curr.forEach(m => { const g = posGroup(m.pos); groups[g] = (groups[g] || 0) + 1; });
      const supply = Object.entries(groups).sort((a, b) => b[1] - a[1])
        .map(([g, n]) => `<div class="fa-rail-row"><span>${esc(g)}</span><span class="fa-rail-num">${n}</span></div>`).join("");
      const supplyMod = supply ? `<div class="fa-rail-mod"><div class="fa-rail-head" title="Current filtered pool by position group">Pool supply</div>${supply}</div>` : "";
      return `<aside class="fa-board-rail">${stampMod}${warMod}${surMod}${supplyMod}</aside>`;
    }
    // Card-head columns must mirror the .proj-card grid exactly, so the two
    // share one track definition rather than two that can drift apart.
    // minmax(0,...) on the one flexible track: a bare fr refuses to shrink below
    // min-content, so a long name would push the numbers off the card.
    const CARD_TRACKS = "34px minmax(0,1.9fr) 92px 84px 52px 96px";
    // Every header is sortable now, including rank and name, and each is a real
    // keyboard button with aria-sort. The old board exposed sorting on the
    // season cells, 5y WAR and Surplus only, and none of them were reachable by
    // keyboard, which made Projections the one module below the a11y contract
    // that fa.js, mlbstats.js and prospx all already met.
    const cardHead = (label, key, title) => {
      const active = state.sort === key;
      const aria = active ? (state.dir < 0 ? "descending" : "ascending") : "none";
      return `<span role="button" tabindex="0" data-psort="${key}" aria-sort="${aria}"${title ? ` title="${esc(title)}"` : ""}>${label}${active ? (state.dir < 0 ? " ▾" : " ▴") : ""}</span>`;
    };
    // The row-2 tape chips are NOT track-aligned with the header (they live in
    // the reserved band at the card bottom and scroll inside their own box), so
    // they get their own strip of sort buttons - the /fantasy/ .ff-sortbar
    // pattern. The per-season keys y0..y4 have existed in sortRows since the
    // board was a table, but nothing in the UI reached them after the card
    // conversion: they were only addressable by hand-editing #sort=y0 into the
    // URL. This is where they come back, and they follow the active cell metric
    // (WAR / wRC+ / wOBA / FIP) the same way the chips do.
    const cellLbl = state.cells === "war" ? "WAR" : RATE_META[state.cells].label;
    const tapeSortbar = `<div class="mlb-sortbar"><span class="mlb-sortbar-lbl">Sort tape</span>
      ${seasons.map((s, t) => cardHead(String(s), "y" + t, `Sort by the ${s} cell (currently ${cellLbl})`)).join("")}
      ${cardHead("peak WAR", "warPeak", "Talent-path projection at peak age")}
      ${cardHead("contract thru", "thru", "Final guaranteed season on the contract on file. Prospects and unsigned players sort last.")}
    </div>`;
    root.innerHTML = `<div class="fa-board-layout"><div class="fa-board-main">` + warMap + tapeSortbar + `
      <div class="mlb-card-head" style="grid-template-columns:${CARD_TRACKS};">
        ${cardHead("#", "rank", "Board position under the current sort")}
        ${cardHead("Player", "name", "Sort by name")}
        ${cardHead(`${DATA.horizon}y WAR`, "warTotal", "Projected bWAR over the window, playing-time-held (if-healthy) path, with the P10-P90 outcome band. Surplus prices the attrition-discounted expected value, not this path.")}
        ${cardHead("AAV", "aav", "Average annual value of the guaranteed contract on file. Prospects and players without a multi-year deal carry none.")}
        ${cardHead("Age", "age", "Sort by age - the aging curves run forward from it")}
        ${cardHead("Surplus", "sur", "Veterans: production value minus salary, salary-known seasons only. Prospects: platform surplus value.")}
      </div>
      <div class="mlb-card-list" style="--card-tracks:${CARD_TRACKS};">${body || `<div class="fa-sub proj-empty">No players match.</div>`}</div>
      ${list.length > state.limit ? `<div class="proj-more-wrap"><button class="chip" id="proj-more">show ${Math.min(100, list.length - state.limit)} more (${list.length - state.limit} hidden)</button></div>` : ""}</div>${projBoardSidebar(list)}</div>`;
    // One place sets the card grid, from the same string the header uses.
    root.querySelectorAll(".proj-card").forEach(c => { c.style.gridTemplateColumns = CARD_TRACKS; });
    // Keyboard parity for EVERY sort affordance (click is wired below). This
    // selector was scoped to .mlb-card-head, which would have left the new tape
    // sort bar mouse-only - the exact a11y hole this pattern exists to close.
    root.querySelectorAll("[data-psort]").forEach(h => {
      h.onkeydown = e => {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); h.click(); }
      };
    });
    // Whole-card activation, matching the PROSPX row behaviour. Ignore clicks
    // that landed on a control inside the card (the compare button, any link).
    root.querySelectorAll(".proj-card[data-card-href]").forEach(c => {
      const open = () => { location.href = c.dataset.cardHref; };
      c.onclick = e => { if (!e.target.closest("a,button")) open(); };
      c.onkeydown = e => {
        if ((e.key === "Enter" || e.key === " ") && !e.target.closest("a,button")) { e.preventDefault(); open(); }
      };
    });
    root.querySelectorAll("[data-psort]").forEach(h => h.onclick = () => {
      const k = h.dataset.psort;
      if (state.sort === k) state.dir = -state.dir;
      else { state.sort = k; state.dir = -1; }
      syncToURL(); renderTable();
    });
    ["proj-sx", "proj-sy"].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.onchange = () => {
        state[id === "proj-sx" ? "sx" : "sy"] = el.value;
        syncToURL(); renderTable();
        const d = root.querySelector("details.proj-warmap");
        if (d) d.open = true;   // keep the chart open across the re-render
      };
    });
    const more = document.getElementById("proj-more");
    if (more) more.onclick = () => { state.limit += 100; renderTable(); };
    root.querySelectorAll("[data-cmp-key]").forEach(b => b.onclick = () => {
      const k = b.dataset.cmpKey;
      const i = state.cmp.indexOf(k);
      if (i >= 0) state.cmp.splice(i, 1);
      else { state.cmp.push(k); if (state.cmp.length > 2) state.cmp.shift(); }
      syncToURL();
      if (state.cmp.length === 2) render(); else renderTable();
    });
    // Cross-module cohesion: FA-class members get a $ chip linking to
    // their market card (async via the links map; no layout shift).
    if (window.EEPHUS_HUB) {
      window.EEPHUS_HUB.links().then(L => {
        if (!L) return;
        root.querySelectorAll(".proj-fa-slot[data-fa-key]").forEach(el => {
          const row = (L.byKey || {})[el.dataset.faKey];
          if (row && row.fa) {
            el.innerHTML = ` <a class="proj-tag" href="/fa/#player=${encodeURIComponent(row.key)}" title="In the current FA class - open the market card (projected deal, verdict, comps)">$ FA</a>`;
          }
          el.removeAttribute("data-fa-key");
        });
      });
    }
    if (window.EEPHUS_GL) window.EEPHUS_GL.wire(root);
  }

  // ===========================================================================
  // Head-to-head compare (#cmp=a,b) - two board rows side by side: overlaid
  // projection paths, season-aligned WAR table with the edge per season,
  // value tiles. Works across sources (vet vs prospect compares fine -
  // warAt aligns both to calendar seasons).
  // ===========================================================================
  function findRow(key) {
    return (DATA.vets || []).concat(DATA.prospects || []).find(m => m.key === key) || null;
  }
  function renderCompare() {
    const root = document.getElementById("proj-rows");
    const bar = document.getElementById("proj-filters");
    const banner = document.getElementById("proj-banner");
    if (banner) banner.innerHTML = "";
    const a = findRow(state.cmp[0]), b = findRow(state.cmp[1]);
    bar.innerHTML = `<a class="chip" href="#" id="cmp-back">← back to projections</a>
      <button class="chip egfx-chip" id="cmp-gfx" title="Generate a shareable graphic (theme-aware)"><span class="egfx-chip-glyph" aria-hidden="true">&#9636;</span>Generate GFX</button>`;
    document.getElementById("cmp-back").onclick = (e) => {
      e.preventDefault(); state.cmp = []; syncToURL(); render();
    };
    if (!a || !b) {
      root.innerHTML = `<div class="state-message">Compare pair not found. <a href="#" onclick="location.hash='';return false;">Back</a>.</div>`;
      return;
    }
    const first = DATA.first_season;
    const seasons = Array.from({ length: DATA.horizon }, (_, t) => first + t);
    const CA = "var(--accent-cyan)", CB = "var(--accent-gold)";
    // overlaid mean paths (bands omitted - two bands over each other is mud;
    // the table below carries the totals band)
    const wA = seasons.map((_, t) => warAt(a, t)), wB = seasons.map((_, t) => warAt(b, t));
    const all = wA.concat(wB).filter(v => v != null);
    const W = 560, H = 180, PX = 36, PY = 16;
    const mn = Math.min(0, ...all), mx = Math.max(1, ...all);
    const x = t => PX + t * (W - PX - 8) / Math.max(1, seasons.length - 1);
    const y = v => PY + (mx - v) * (H - PY - 24) / (mx - mn || 1);
    const line = (w, color) => {
      const pts = w.map((v, t) => v != null ? `${x(t)},${y(v)}` : null).filter(Boolean).join(" ");
      return pts ? `<polyline points="${pts}" fill="none" stroke="${color}" stroke-width="2.5" stroke-linejoin="round"/>` : "";
    };
    const dots = (w, color, nm) => w.map((v, t) => v != null
      ? `<circle cx="${x(t)}" cy="${y(v)}" r="3" fill="${color}"><title>${esc(nm)} ${seasons[t]}: ${fmtWar(v)}</title></circle>` : "").join("");
    const ticks = seasons.map((s, t) => `<text x="${x(t)}" y="${H - 6}" text-anchor="middle" class="mlbp-fan-tick">${s}</text>`).join("");
    const zero = mn < 0 ? `<line x1="${PX}" x2="${W - 8}" y1="${y(0)}" y2="${y(0)}" class="mlbp-fan-zero"/>` : "";
    const chart = `<svg class="mlbp-fan" viewBox="0 0 ${W} ${H}" role="img" aria-label="Projected WAR comparison">
      ${zero}${line(wA, CA)}${line(wB, CB)}${dots(wA, CA, a.name)}${dots(wB, CB, b.name)}${ticks}</svg>`;
    // Only the name COLOUR stays inline - it is the per-side series colour the
    // chart already draws with. The ellipsizing box lives on .proj-cmp-name.
    const head = (m, color) => `<div class="proj-cmp-head">
      ${teamLogo(m.team)}<strong class="proj-cmp-name" style="color:${color};">${esc(m.name)}</strong>
      <span class="fa-sub">${esc(m.pos || "")} · ${m.age != null ? Math.floor(m.age) : "?"}${m.team ? "" : " · FA"}</span>${tagFor(m)}</div>`;
    const seasonRows = seasons.map((s, t) => {
      const va = warAt(a, t), vb = warAt(b, t);
      const edge = (va != null && vb != null) ? va - vb : null;
      const cell = (v, m) => v == null
        ? `<td class="proj-dim">${m.src === "prospect" && s < m.eta ? "MiLB" : EM_DASH}</td>`
        : `<td class="proj-war${warClass(v)}">${fmtWar(v)}</td>`;
      return `<tr><td>${s}</td>${cell(va, a)}${cell(vb, b)}
        <td class="${edge == null ? "proj-dim" : edge >= 0 ? "proj-pos" : "proj-neg"}">${edge == null ? EM_DASH : (edge >= 0 ? "+" : "") + edge.toFixed(1)}</td></tr>`;
    }).join("");
    const totRow = (label, va, vb, fmt) => {
      const d = (va != null && vb != null) ? va - vb : null;
      return `<tr class="proj-cmp-total"><td>${label}</td><td>${va != null ? fmt(va) : EM_DASH}</td><td>${vb != null ? fmt(vb) : EM_DASH}</td>
        <td class="${d == null ? "proj-dim" : d >= 0 ? "proj-pos" : "proj-neg"}">${d == null ? EM_DASH : (d >= 0 ? "+" : "") + (fmt === fmtWar ? d.toFixed(1) : money(d))}</td></tr>`;
    };
    root.innerHTML = `<div class="mlbp-page">
      <div class="mlbp-section proj-cmp-section">
        <div class="mlbp-section-title">Head-to-Head <span class="fa-sub">projected mean bWAR, season-aligned${(a.src === "prospect" || b.src === "prospect") ? " · prospects join at their PROSPX ETA" : ""}</span></div>
        <div class="proj-cmp-heads">${head(a, CA)}${head(b, CB)}</div>
        ${chart}
        <table class="detail-table proj-table proj-cmp-table">
          <thead><tr><th>Season</th><th style="color:${CA};">${esc(a.name)}</th><th style="color:${CB};">${esc(b.name)}</th><th>Edge</th></tr></thead>
          <tbody>${seasonRows}
            ${totRow(`${DATA.horizon}y WAR`, warShown(a), warShown(b), fmtWar)}
            ${totRow("Surplus", surOf(a), surOf(b), money)}</tbody></table>
        <div class="fa-note proj-cmp-note">Edge = left minus right, per season. Totals carry each player's own P10-P90 band on the board view. Surplus compares different things across sources (veteran contract surplus vs prospect control-window surplus) - read it as "value above cost," not like-for-like contract terms.</div>
      </div></div>`;
    const gfx = document.getElementById("cmp-gfx");
    if (gfx) gfx.onclick = () => {
      if (!window.EEPHUS_HUB) return;
      // Declarative since GFX slice 4: the "compare" template owns the
      // no-tiles / two-column layout; this site only supplies the columns.
      window.EEPHUS_HUB.openCard({
        template: "compare",
        data: { columns: [
          { title: esc(a.name), rows: seasons.map((s, t) => [String(s), fmtWar(warAt(a, t))]) },
          { title: esc(b.name), rows: seasons.map((s, t) => [String(s), fmtWar(warAt(b, t))]) },
        ] },
        module: "MLB Projections",
        accentToken: "--accent-cyan",
        name: `${a.name} vs ${b.name}`,
        meta: `head-to-head · projected ${DATA.horizon}y bWAR ${fmtWar(warShown(a))} vs ${fmtWar(warShown(b))}`,
        url: "eephus.io/projections",
        filename: `eephus-cmp-${a.key}-${b.key}.png`,
        caption: "eephus projection engine (proj_lgbm_v1) · season-aligned mean bWAR",
      });
    };
    if (window.EEPHUS_GL) window.EEPHUS_GL.wire(root);
  }

  // ===========================================================================
  // MLB player page (#player={key}) - the per-player detail surface
  // (data/mlb_player_detail.json, mlb_player_export.py). Parity goal with
  // prospect detail: hero + tiles, projection fan, Savant percentile
  // sliders, pitch arsenal, season-by-season career with bWAR, FA market
  // block for class members.
  // ===========================================================================
  function headshotURL(mlbam, r) {
    return `https://img.mlbstatic.com/mlb-photos/image/upload/d_people:generic:headshot:67:current.png/w_${r || 240},q_auto:best/v1/people/${mlbam}/headshot/67/current`;
  }
  function pctClass(p) {
    return p >= 80 ? "is-elite" : p >= 60 ? "is-good" : p >= 40 ? "is-avg" : p >= 20 ? "is-low" : "is-poor";
  }
  function sliders(sc) {
    if (!sc || !sc.metrics || !sc.metrics.length) return "";
    const rows = sc.metrics.map(m => `
      <div class="mlbp-slider">
        <span class="mlbp-slider-label">${esc(m.label)}</span>
        <div class="mlbp-slider-track"><div class="mlbp-slider-fill ${pctClass(m.pct)}" style="width:${m.pct}%;"></div>
          <span class="mlbp-slider-pct ${pctClass(m.pct)}" style="left:${Math.min(94, Math.max(2, m.pct))}%;">${m.pct}</span></div>
        <span class="mlbp-slider-val">${esc(m.value)}</span>
      </div>`).join("");
    return `<div class="mlbp-section"><div class="mlbp-section-title">Statcast Percentiles <span class="fa-sub">${sc.season} · vs qualified MLB pool</span></div>${rows}</div>`;
  }
  function fanChart(p) {
    const war = (p.proj && p.proj.war) || [];
    if (war.length < 2) return "";
    const lo = (p.proj && p.proj.warP10) || [], hi = (p.proj && p.proj.warP90) || [];
    const first = DATA.first_season, W = 560, H = 170, PX = 36, PY = 16;
    const all = war.concat(lo, hi).filter(v => v != null);
    const mn = Math.min(0, ...all), mx = Math.max(1, ...all);
    const x = t => PX + t * (W - PX - 8) / (war.length - 1);
    const y = v => PY + (mx - v) * (H - PY - 24) / (mx - mn || 1);
    const pts = a => a.map((v, t) => `${x(t)},${y(v)}`).join(" ");
    const band = (lo.length && hi.length)
      ? `<polygon points="${pts(hi)} ${lo.map((v, t) => `${x(lo.length - 1 - t)},${y(lo[lo.length - 1 - t])}`).join(" ")}" class="mlbp-fan-band"/>` : "";
    const ticks = war.map((v, t) => `<text x="${x(t)}" y="${H - 6}" text-anchor="middle" class="mlbp-fan-tick">${first + t}</text>`).join("");
    const zero = (mn < 0) ? `<line x1="${PX}" x2="${W - 8}" y1="${y(0)}" y2="${y(0)}" class="mlbp-fan-zero"/>` : "";
    return `<div class="mlbp-section"><div class="mlbp-section-title">Projected bWAR <span class="fa-sub">mean + P10-P90 band · expected (attrition-discounted) path, the one surplus prices</span></div>
      <svg class="mlbp-fan" viewBox="0 0 ${W} ${H}" role="img" aria-label="Projected WAR path">${band}
        <polyline points="${pts(war)}" class="mlbp-fan-line"/>
        ${war.map((v, t) => `<circle cx="${x(t)}" cy="${y(v)}" r="3" class="mlbp-fan-dot"><title>${first + t}: ${fmtWar(v)}${lo[t] != null ? ` (${fmtWar(lo[t])}-${fmtWar(hi[t])})` : ""}</title></circle>`).join("")}
        ${zero}${ticks}</svg></div>`;
  }
  // Explicit upside read-out: the per-year P90 (ceiling) path, each season
  // labeled on its own. Per-year quantiles are NOT additive, so this element
  // never shows a multi-year P90 total (the sum of per-year P90s is not the
  // P90 of the total; see the F-01 ledger note).
  function upsidePath(p) {
    const hi = (p.proj && p.proj.warP90) || [];
    if (!hi.length || !hi.some(v => v != null)) return "";
    const first = DATA.first_season;
    const cells = hi.map((v, t) => `<div class="mlbp-cell"><span class="mlbp-cell-label">${first + t}</span><span class="mlbp-cell-val${warClass(v)}">${fmtWar(v)}</span></div>`).join("");
    return `<div class="mlbp-section"><div class="mlbp-section-title">Upside <span class="fa-sub">P90 outcome per season - the year-by-year ceiling if things break right (per-year percentiles; they do not add up to a multi-year total)</span></div>
      <div class="mlbp-grid mlbp-grid-flow">${cells}</div></div>`;
  }
  function arsenalTable(ar) {
    if (!ar || !ar.length) return "";
    return `<div class="mlbp-section"><div class="mlbp-section-title">Pitch Arsenal <span class="fa-sub">usage · run value /100 · whiff%</span></div>
      <table class="detail-table"><thead><tr><th>Pitch</th><th>Usage</th><th>RV/100</th><th>Whiff%</th><th>BA against</th></tr></thead>
      <tbody>${ar.map(a => `<tr><td>${esc(a.pitch || "")}</td><td>${a.usage != null ? a.usage.toFixed(1) + "%" : EM_DASH}</td>
        <td class="${a.rv100 != null && a.rv100 < 0 ? "proj-pos" : a.rv100 > 0 ? "proj-neg" : ""}">${a.rv100 != null ? a.rv100.toFixed(1) : EM_DASH}</td>
        <td>${a.whiff != null ? a.whiff.toFixed(1) + "%" : EM_DASH}</td><td>${a.ba != null ? String(a.ba) : EM_DASH}</td></tr>`).join("")}</tbody></table></div>`;
  }
  function careerTable(p) {
    const c = p.career || [];
    if (!c.length) return "";
    const head = p.isPit
      ? "<th>Year</th><th>IP</th><th>ERA</th><th>K%</th><th>BB%</th><th>bWAR</th>"
      : "<th>Year</th><th>PA</th><th>AVG/OBP/SLG</th><th>OPS</th><th>HR</th><th>SB</th><th>BB%</th><th>K%</th><th>ISO</th><th>bWAR</th>";
    const rows = c.slice().reverse().map(r => p.isPit
      ? `<tr><td>${r.y}</td><td>${r.ip ?? EM_DASH}</td><td>${r.era != null ? r.era.toFixed(2) : EM_DASH}</td><td>${r.kPct != null ? r.kPct + "%" : EM_DASH}</td><td>${r.bbPct != null ? r.bbPct + "%" : EM_DASH}</td><td>${r.war != null ? r.war.toFixed(1) : EM_DASH}</td></tr>`
      : `<tr><td>${r.y}</td><td>${r.pa ?? EM_DASH}</td><td>${esc(r.avg || "-")}/${esc(r.obp || "-")}/${esc(r.slg || "-")}</td><td>${esc(r.ops || EM_DASH)}</td><td>${r.hr ?? EM_DASH}</td><td>${r.sb ?? EM_DASH}</td><td>${r.bbPct != null ? r.bbPct + "%" : EM_DASH}</td><td>${r.kPct != null ? r.kPct + "%" : EM_DASH}</td><td>${r.iso != null ? String(r.iso).replace(/^0(?=\.)/, "") : EM_DASH}</td><td>${r.war != null ? r.war.toFixed(1) : EM_DASH}</td></tr>`).join("");
    return `<div class="mlbp-section"><div class="mlbp-section-title">Career <span class="fa-sub">MLB seasons · bWAR (Baseball-Reference)</span></div>
      <table class="detail-table"><thead><tr>${head}</tr></thead><tbody>${rows}</tbody></table></div>`;
  }
  function faBlock(p) {
    const f = p.fa;
    if (!f) return "";
    const verd = f.verdict ? `<span class="mlbp-tile-chip">${esc(f.verdict)}</span>` : "";
    const cells = [
      ["Projected", f.projYears != null ? `${f.projYears}y / ${money(f.projGuar)}` : EM_DASH],
      ["Proj AAV", f.projAav != null ? `${money(f.projAav)}${f.projAavP10 != null ? ` <span class="fa-band">(${money(f.projAavP10)}-${money(f.projAavP90)})</span>` : ""}` : EM_DASH],
      ["Rational value", f.rational != null ? money(f.rational) : EM_DASH],
      ["Contract surplus", f.surplus != null ? money(f.surplus) : EM_DASH],
      ["Deal+", f.dealPlus != null ? String(Math.round(f.dealPlus)) : EM_DASH],
      ["Prior AAV", f.prevAav != null ? money(f.prevAav) : EM_DASH],
    ];
    return `<div class="mlbp-section"><div class="mlbp-section-title">Free Agency <span class="fa-sub">${esc(f.status || "")} · gate-validated market model</span> ${verd}</div>
      <div class="mlbp-grid">${cells.map(([l, v]) => `<div class="mlbp-cell"><span class="mlbp-cell-label">${l}</span><span class="mlbp-cell-val">${v}</span></div>`).join("")}</div>
      <div class="fa-sub mlbp-block-foot"><a class="fa-player-link" href="/fa/#player=${encodeURIComponent(p.key)}">market card on the class board →</a></div></div>`;
  }
  // ---- bat-speed change -----------------------------------------------------
  // MLB bat tracking starts in 2024, so a year-over-year Swing+ delta exists ONLY
  // for hitters with a scored season on BOTH sides of the latest pair. That is a
  // small, named population (the payload reports exactly how many), and every
  // other hitter gets an explicit no-data state instead of a chip that implies
  // coverage we do not have.
  //
  // The alert cut is the 10th percentile of the MEASURED delta distribution in
  // that same population, carried on the payload - a distributional flag, not a
  // validated predictor of anything. Nothing here claims a decline forecasts
  // decline; it says this season's swing is in the bottom tenth of observed
  // year-over-year changes.
  function ensureSwingDelta(key) {
    if (SWINGD || SWINGD_LOADING) return;
    SWINGD_LOADING = true;
    fetch("/data/swing_delta.json", { cache: "no-cache" })
      .then(r => (r.ok ? r.json() : null))
      .then(d => {
        SWINGD = d || { players: {} };
        SWINGD_LOADING = false;
        if (state.player === key) renderPlayer(key);
      })
      .catch(() => { SWINGD = { players: {} }; SWINGD_LOADING = false; });
  }

  function batSpeedChip(p) {
    if (p.isPit && !p.twoWay) return "";           // bat tracking is a hitter read
    if (!SWINGD || !SWINGD.players) return "";
    const yrs = (SWINGD.priorSeason && SWINGD.latestSeason)
      ? `${String(SWINGD.priorSeason).slice(2)}&rarr;${String(SWINGD.latestSeason).slice(2)}` : "";
    const row = p.mlbam != null ? SWINGD.players[String(p.mlbam)] : null;
    const wrap = (cls, body, title) =>
      `<div class="mlbp-batspeed ${cls}" title="${esc(title)}">${body}</div>`;
    if (!row) {
      // Two distinct no-data cases, said plainly rather than blended.
      const why = (SWINGD.latestSeason && p.swingPlusSeasons
                   && (p.swingPlusSeasons[String(SWINGD.latestSeason)] || {}).swing_plus != null)
        ? `no ${SWINGD.priorSeason} bat-tracking season to compare against`
        : "no scored bat-tracking pair for this hitter";
      return wrap("is-nodata",
        `<span class="mlbp-batspeed-label">Bat speed ${yrs}</span><span class="mlbp-batspeed-val">no data</span>`
        + `<span class="mlbp-batspeed-why">${esc(why)}</span>`,
        `Swing+ year-over-year change needs a scored season on both sides. Only ${SWINGD.n} hitters have one `
        + `(${SWINGD.nLatestOnly} more have ${SWINGD.latestSeason} only). MLB bat tracking begins in 2024 and there is no minor-league equivalent.`);
    }
    const cut = (SWINGD.dist || {}).p10;
    const alert = (cut != null && row.d <= cut);
    const sign = row.d > 0 ? "+" : "";
    const body = `<span class="mlbp-batspeed-label">Bat speed ${yrs}</span>`
      + `<span class="mlbp-batspeed-val">${sign}${row.d.toFixed(1)}</span>`
      + `<span class="mlbp-batspeed-why">Swing+ ${row.prior.toFixed(1)} &rarr; ${row.latest.toFixed(1)}`
      + `${row.lowN ? " &middot; partial tracking" : ""}</span>`
      + (alert ? `<span class="mlbp-batspeed-flag">bottom decile</span>` : "");
    const title = `Swing+ moved ${sign}${row.d.toFixed(1)} from ${SWINGD.priorSeason} (n=${row.nPrior} swings) to `
      + `${SWINGD.latestSeason} (n=${row.nLatest}). Across the ${SWINGD.n} hitters with both seasons the median change is `
      + `${(SWINGD.dist || {}).p50}, the 10th percentile ${cut} and the 90th ${(SWINGD.dist || {}).p90}. `
      + (alert ? "This change sits in the bottom tenth of that distribution. " : "")
      + "A description of an observed change, not a projection: nothing here has been tested as a predictor."
      + (row.lowN ? ` One of the two seasons is under ${SWINGD.minSwings} swings, so the model shrank it hard toward 100.` : "");
    return wrap(alert ? "is-alert" : "", body, title);
  }

  function ensureFielding(key) {
    if (FIELDING || FIELDING_LOADING) return;
    FIELDING_LOADING = true;
    fetch("/data/mlb_fielding_positions.json", { cache: "no-cache" })
      .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
      .then(d => {
        FIELDING = d || {};
        FIELDING_LOADING = false;
        if (state.player === key) renderPlayer(key);
      })
      .catch(() => { FIELDING = { players: {} }; FIELDING_LOADING = false; });
  }
  // Live season pitching from the /mlbstats/ leaderboards (REM+ / RIV+ for
  // relievers, SEM+ for starters), joined by MLBAM. Lazy-loaded once and cached,
  // then the player page re-renders (same pattern as ensureFielding). This rolls
  // the current-season pitching skill/impact ratings into the MLB player card.
  function ensurePitchingStats(key) {
    if (PITCHLB || PITCHLB_LOADING) return;
    PITCHLB_LOADING = true;
    const byMlbam = {};
    const grab = (url, kind) => fetch(url, { cache: "no-cache" })
      .then(r => (r.ok ? r.json() : null))
      .then(d => {
        const rows = (d && (d.relievers || d.starters)) || [];
        const season = d && d.season;
        rows.forEach(row => { if (row.mlbam != null) byMlbam[row.mlbam] = { kind, season, row }; });
      })
      .catch(() => {});
    Promise.all([
      grab("/data/bullpen_leaderboards.json", "rel"),
      grab("/data/starter_leaderboards.json", "sp"),
    ]).then(() => {
      PITCHLB = { byMlbam };
      PITCHLB_LOADING = false;
      if (state.player === key) renderPlayer(key);
    });
  }
  function pitchingStatsBlock(p) {
    if (!p || p.mlbam == null) return "";
    // Prefer the baked skills block (mlb_player_export); fall back to the
    // client-fetched leaderboard row for payloads generated before it was baked.
    let kind, season, role, ip, remPlus, rivPlus, remPlus3yr, semPlus, semPlus3yr;
    let xremPlus, xsemPlus, warIpPlus, warIpPlusAdj, warIpPlusPct, gmli, saves, holds;
    if (p.skills && p.skills.pitch) {
      const s = p.skills.pitch;
      kind = s.kind; season = s.season; role = s.role; ip = s.ip;
      remPlus = s.remPlus; rivPlus = s.rivPlus; remPlus3yr = s.remPlus3yr;
      semPlus = s.semPlus; semPlus3yr = s.semPlus3yr;
      xremPlus = s.xremPlus; xsemPlus = s.xsemPlus;
      warIpPlus = s.warIpPlus; warIpPlusAdj = s.warIpPlusAdj;
      warIpPlusPct = s.warIpPlusPct; gmli = s.gmli;
      saves = s.saves; holds = s.holds;
    } else if (PITCHLB && PITCHLB.byMlbam && PITCHLB.byMlbam[p.mlbam]) {
      const hit = PITCHLB.byMlbam[p.mlbam], r = hit.row;
      kind = hit.kind; season = hit.season; role = r.role; ip = r.ip;
      remPlus = r.rem_plus; rivPlus = r.riv_plus; remPlus3yr = r.rem_plus_3yr;
      semPlus = r.sem_plus; semPlus3yr = r.sem_plus_3yr;
      xremPlus = r.xrem_plus; xsemPlus = r.xsem_plus;
      warIpPlus = r.war_ip_plus; warIpPlusAdj = r.war_ip_plus_adj;
      warIpPlusPct = r.war_ip_plus_pct; gmli = r.gmli;
      saves = r.saves; holds = r.holds;
    } else return "";
    const plus = (label, val, hi) => (val == null ? "" :
      `<div class="mlbp-tile"><span class="mlbp-tile-label">${label}</span><span class="mlbp-tile-val ${val >= (hi || 105) ? "proj-pos" : val <= (200 - (hi || 105)) ? "proj-neg" : ""}">${val}</span></div>`);
    // WAR/IP+ is 100 + 10z, so it bands at 80/120 (two pool sigma) rather than the
    // 105/95 the ratio-scale REM+/SEM+ family uses. Separate helper so the two
    // rulers cannot drift into each other.
    const zplus = (label, val, title) => (val == null ? "" :
      `<div class="mlbp-tile"${title ? ` title="${esc(title)}"` : ""}><span class="mlbp-tile-label">${label}</span><span class="mlbp-tile-val ${val >= 120 ? "proj-pos" : val <= 80 ? "proj-neg" : ""}">${val}</span></div>`);
    const raw = (label, val, title) => (val == null ? "" :
      `<div class="mlbp-tile"${title ? ` title="${esc(title)}"` : ""}><span class="mlbp-tile-label">${label}</span><span class="mlbp-tile-val">${val}</span></div>`);
    const WAR_IP_TIP = "Pitching bWAR per inning, indexed so 100 is average and every TEN points is one standard deviation of the pool. Anchored on this pitcher's own role pool, so a starter's value and a reliever's are not comparable.";
    let tiles = "", n = "";
    if (kind === "rel") {
      tiles = plus("REM+", remPlus) + plus("RIV+", rivPlus)
        + (remPlus3yr != null ? plus("REM+ 3yr", remPlus3yr) : "")
        + plus("xREM+", xremPlus)
        + zplus("WAR/IP+", warIpPlus, WAR_IP_TIP + (warIpPlusPct != null ? ` Percentile: ${warIpPlusPct}.` : ""))
        + zplus("WAR/IP+ adj", warIpPlusAdj, "The same index regressed toward the pool rate by innings, so a short hot stretch does not outrank a full season. Relief innings totals are small enough that this matters most here.")
        + raw("gmLI", gmli == null ? null : gmli.toFixed(2), "Average leverage index when he ENTERS a game: how big the moments are that his manager trusts him with. 1.00 is a neutral spot.");
      n = `${role || "reliever"}${ip != null ? ` · ${ip} IP` : ""}`
        + (saves != null || holds != null ? ` · ${saves || 0} SV / ${holds || 0} HLD` : "");
    } else {
      tiles = plus("SEM+", semPlus) + (semPlus3yr != null ? plus("SEM+ 3yr", semPlus3yr) : "")
        + plus("xSEM+", xsemPlus)
        + zplus("WAR/IP+", warIpPlus, WAR_IP_TIP + (warIpPlusPct != null ? ` Percentile: ${warIpPlusPct}.` : ""))
        + zplus("WAR/IP+ adj", warIpPlusAdj, "The same index regressed toward the pool rate by innings, so a short hot stretch does not outrank a full season.");
      n = `${role || "starter"}${ip != null ? ` · ${ip} IP` : ""}`;
    }
    // Leverage: descriptive game-context, kept in its own line rather than mixed
    // into the plus tiles above, because none of it is on a plus scale.
    const L = (p.skills && p.skills.lev) || null;
    if (L && (L.wpa != null || L.clutch != null)) {
      const bits = [];
      if (L.wpa != null) bits.push(`WPA ${L.wpa > 0 ? "+" : ""}${L.wpa.toFixed(2)}`);
      if (L.wpaLi != null) bits.push(`WPA/LI ${L.wpaLi > 0 ? "+" : ""}${L.wpaLi.toFixed(2)}`);
      if (L.pli != null) bits.push(`pLI ${L.pli.toFixed(2)}`);
      if (L.clutch != null) bits.push(`Clutch ${L.clutch > 0 ? "+" : ""}${L.clutch.toFixed(2)}`);
      if (L.wpaPerStart != null) bits.push(`WPA/start ${L.wpaPerStart > 0 ? "+" : ""}${L.wpaPerStart.toFixed(3)}`);
      if (bits.length) n += ` · ${bits.join(" · ")}`;
    }
    if (!tiles) return "";
    const seasonTxt = season ? `${season} ` : "";
    return `<div class="mlbp-section-title mlbp-subhead">Live pitching <span class="fa-sub mlbp-subhead-sub">${esc(seasonTxt)}season</span></div>
      <div class="fa-sub mlbp-subhead-note">${esc(n)} · <a class="fa-player-link" href="/mlbstats/">open the MLB Stats leaderboards &rarr;</a></div>
      <div class="mlbp-tiles">${tiles}</div>`;
  }
  // Consensus-FV trajectory as a tiny inline sparkline (ex-PROSPX players). The
  // arc is [[date, fv], ...] baked from the same series the PROSPX FV-history
  // chart draws; here it is a hero-strip glyph next to the FV open->close read.
  function fvSparkSVG(spark) {
    if (!spark || spark.length < 2) return "";
    const vals = spark.map(s => s[1]).filter(v => v != null);
    if (vals.length < 2) return "";
    const W = 108, H = 22, PX = 2, PY = 3;
    const mn = Math.min(...vals), mx = Math.max(...vals);
    const x = i => PX + i * (W - 2 * PX) / (spark.length - 1);
    const y = v => PY + (mx - v) * (H - 2 * PY) / ((mx - mn) || 1);
    const pts = spark.map((s, i) => s[1] != null ? `${x(i).toFixed(1)},${y(s[1]).toFixed(1)}` : null).filter(Boolean).join(" ");
    const last = vals[vals.length - 1];
    // The GEOMETRY plots the raw arc (a rounded path would step, not curve), but
    // every number SAID out loud is a consensus FV, so it displays CEILING per
    // the owner rule. The baked arc is fractional (8,984 of the points in the
    // shipped mlb_player_detail.json are), so this read "FV 67.8" before.
    const fvc = v => (window.EEPHUS_HUB ? EEPHUS_HUB.fvCeil(v) : Math.ceil(v));
    return `<svg class="mlbp-fvspark" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" role="img" aria-label="Consensus FV trajectory, ${fvc(vals[0])} to ${fvc(last)}" preserveAspectRatio="none">
      <polyline points="${pts}" fill="none" stroke="var(--accent-cyan)" stroke-width="1.5" stroke-linejoin="round"/>
      <circle cx="${x(spark.length - 1).toFixed(1)}" cy="${y(last).toFixed(1)}" r="1.8" fill="var(--accent-cyan)"><title>latest consensus FV ${fvc(last)}</title></circle></svg>`;
  }
  // 20-80 scouting-scale color (50 = MLB average). Tool grades display CEILING.
  function gradeColor(v) {
    return v >= 65 ? "var(--up)" : v >= 55 ? "var(--accent-cyan)" : v >= 45 ? "var(--text-secondary)" : "var(--down)";
  }
  const TOOL_PILLS = {
    hit: [["Hit", "hit"], ["Game Pwr", "game_pwr"], ["Raw Pwr", "raw_pwr"], ["Speed", "speed"], ["Field", "field"], ["Arm", "throw"], ["Bat Ctrl", "bat_ctrl"], ["Pitch Sel", "pitch_sel"]],
    pit: [["FB", "fb"], ["SL", "sl"], ["CB", "cb"], ["CH", "ch"], ["CT", "ct"], ["CMD", "cmd"], ["FRM", "frame"], ["ATHL", "athl"]],
  };
  // Scouting slice (ex-PROSPX players): the latest published report blurb + the
  // consensus 20-80 tool grades as pills. Both are conditional - a player with
  // neither renders nothing (no empty shell).
  function scoutingBlock(p) {
    const s = p.scout;
    if (!s) return "";
    let pillsHtml = "";
    if (s.tools) {
      const order = TOOL_PILLS[p.isPit ? "pit" : "hit"];
      const known = new Set(order.map(o => o[1]));
      const extra = Object.keys(s.tools).filter(k => !known.has(k) && s.tools[k] != null).map(k => [k.toUpperCase().replace(/_/g, " "), k]);
      const pills = order.concat(extra).filter(([, k]) => s.tools[k] != null).map(([lbl, k]) => {
        const raw = Number(s.tools[k]);
        const g = Math.ceil(raw);   // owner rule: tool grades display ceiling
        // Only the grade COLOUR stays inline (gradeColor is a value read off the
        // 20-80 grade); the pill shape lives on .mlbp-toolpill.
        return `<span class="mlbp-toolpill">
          <span class="mlbp-toolpill-label">${esc(lbl)}</span>
          <span class="mlbp-toolpill-val" style="color:${gradeColor(raw)};">${g}</span></span>`;
      }).join("");
      if (pills) pillsHtml = `<div class="mlbp-toolpills">${pills}</div>`;
    }
    let reportHtml = "";
    const r = s.report;
    if (r && r.text) {
      reportHtml = `<div class="mlbp-scout-report">
        <div class="fa-sub mlbp-scout-src">${esc(r.source || "Scouting report")}${r.date ? ` · ${esc(r.date)}` : ""}</div>
        <p class="mlbp-scout-text">${esc(r.text)}${r.truncated ? "&hellip;" : ""}${p.origin && p.origin.prospx ? ` <a class="fa-player-link" href="/prospx/#player=${encodeURIComponent(p.origin.prospx)}">full report &rarr;</a>` : ""}</p></div>`;
    }
    if (!pillsHtml && !reportHtml) return "";
    return `<div class="mlbp-section"><div class="mlbp-section-title">Scouting <span class="fa-sub">consensus 20-80 tool grades + latest published report · via PROSPX</span></div>${pillsHtml}${reportHtml}</div>`;
  }
  function positionGamesSummary(key) {
    const entry = FIELDING && FIELDING.players && FIELDING.players[key];
    const positions = entry && entry.positions;
    if (!positions) return "";
    const rows = Object.entries(positions)
      .map(([pos, row]) => ({
        pos,
        games: Number(row && row.games),
        starts: Number(row && row.games_started),
        innings: Number(row && row.innings),
      }))
      .filter(r => Number.isFinite(r.games) && r.games > 0)
      .sort((a, b) => (b.games - a.games) || (b.innings - a.innings) || a.pos.localeCompare(b.pos));
    if (!rows.length) return "";
    const season = FIELDING.season || "current";
    return `<div class="position-usage-strip" title="${esc(String(season))} MLB games by position">
      <span class="position-usage-label">${esc(String(season))} usage</span>
      ${rows.map(r => {
        const title = `${r.pos}: ${r.games} games${Number.isFinite(r.starts) ? `, ${r.starts} starts` : ""}${Number.isFinite(r.innings) ? `, ${r.innings} innings` : ""}`;
        return `<span class="position-usage-chip" title="${esc(title)}"><span>${esc(r.pos)}</span>:${esc(String(r.games))}</span>`;
      }).join("")}
    </div>`;
  }

  // Group the merged card's sections (projection + statcast + stats + contract)
  // into a tabbed layout that mirrors the Prospect Detail Card. The section
  // functions keep their own .mlbp-section wrappers; only non-empty panels get a
  // tab, and the first non-empty panel is active by default. All sections stay in
  // the DOM (hidden panels included), so their async fills still land.
  function mlbpTabs(p, key) {
    const nonEmpty = (h) => !!(h && h.replace(/\s+/g, "").length);
    const twoWayNote = (p.twoWay && p.proj && p.proj.warHit)
      ? `<div class="fa-note">Two-way projection: the path above SUMS both sides per season - hitting ${p.proj.warHit.map(fmtWar).join(" / ")} + pitching ${p.proj.warPit.map(fmtWar).join(" / ")}.</div>` : "";
    const statcast = (p.twoWay ? `<div class="mlbp-section-title mlbp-subhead">As a hitter</div>` : "")
      + sliders(p.sc)
      + ((p.isPit && !p.twoWay) ? arsenalTable(p.arsenal) : "")
      + (p.twoWay ? `<div class="mlbp-section-title mlbp-subhead">As a pitcher</div>${sliders(p.scPit)}${arsenalTable(p.arsenal)}` : "");
    const stats = positionGamesSummary(key) + pitchingStatsBlock(p) + careerTable(p)
      + (p.twoWay && p.careerPit && p.careerPit.length ? careerTable({ ...p, career: p.careerPit, isPit: true }) : "");
    const panels = [
      { id: "proj", label: "Projection", html: fanChart(p) + upsidePath(p) + twoWayNote },
      { id: "statcast", label: "Statcast", html: statcast },
      { id: "stats", label: "Stats & Career", html: stats },
      { id: "scouting", label: "Scouting", html: scoutingBlock(p) },
      { id: "contract", label: "Contract & FA", html: faBlock(p) },
    ].filter((pan) => nonEmpty(pan.html));
    // Discussion (per-player thread). Gated on the forum layer being loaded so a
    // build without it never leaves an empty shell; the layer itself paints a
    // quiet "No comments yet" state when Supabase config is blank.
    if (window.EephusUI && typeof window.EephusUI.mountForum === "function")
      panels.push({ id: "discussion", label: "Discussion", html: '<div id="eph-forum-mount"></div>' });
    if (!panels.length) return "";
    // The active/inactive read is carried by aria-selected ALONE: the strip's
    // layout is .mlbp-tabs and the dimmed state is .mlbp-tab[aria-selected="false"]
    // in the stylesheet. It used to be an inline opacity written here and
    // rewritten in bindMlbpTabs, which meant the visual state and the accessible
    // state were two facts that had to be kept in agreement by hand.
    const strip = panels.length > 1
      ? `<div class="mlbp-tabs" role="tablist">${panels.map((pan, i) => `<button type="button" class="chip mlbp-tab" data-mlbp-tab="${pan.id}" role="tab" aria-selected="${i === 0}">${pan.label}</button>`).join("")}</div>`
      : "";
    const body = panels.map((pan, i) => `<div class="mlbp-tabpanel" data-mlbp-panel="${pan.id}"${i === 0 ? "" : " hidden"}>${pan.html}</div>`).join("");
    return strip + body;
  }

  function bindMlbpTabs(root, p, key) {
    // Mount the forum thread the first time the Discussion tab is opened (the
    // account/forum layer loads it only while that tab is active - the prospect
    // page uses the same lazy pattern). No-op without the layer.
    let forumMounted = false;
    const maybeMountForum = (id) => {
      if (id !== "discussion" || forumMounted) return;
      if (!(window.EephusUI && window.EephusUI.mountForum)) return;
      forumMounted = true;
      try { window.EephusUI.mountForum("mlb", key, { name: p.name, player_name: p.name, key: key }); }
      catch (e) { /* non-fatal */ }
    };
    const active = root.querySelector("[data-mlbp-panel]:not([hidden])");
    if (active) maybeMountForum(active.getAttribute("data-mlbp-panel"));
    const tabs = root.querySelectorAll("[data-mlbp-tab]");
    if (!tabs.length) return;
    tabs.forEach((t) => t.addEventListener("click", () => {
      const id = t.getAttribute("data-mlbp-tab");
      root.querySelectorAll("[data-mlbp-tab]").forEach((b) => {
        // aria-selected is the ONLY thing toggled: the stylesheet dims the
        // unselected tabs off that attribute, so there is no second copy of the
        // state to fall out of sync with the accessible one.
        b.setAttribute("aria-selected", b.getAttribute("data-mlbp-tab") === id ? "true" : "false");
      });
      root.querySelectorAll("[data-mlbp-panel]").forEach((pane) => {
        if (pane.getAttribute("data-mlbp-panel") === id) pane.removeAttribute("hidden");
        else pane.setAttribute("hidden", "hidden");
      });
      maybeMountForum(id);
    }));
  }

  function renderPlayer(key) {
    const root = document.getElementById("proj-rows");
    const bar = document.getElementById("proj-filters");
    const banner = document.getElementById("proj-banner");
    if (banner) banner.innerHTML = "";
    if (bar) bar.innerHTML = `<a class="chip" href="#" id="mlbp-back">← back to projections</a>`;
    const back = document.getElementById("mlbp-back");
    if (back) back.onclick = (e) => { e.preventDefault(); state.player = null; syncToURL(); render(); };
    if (!DETAIL) {
      root.innerHTML = `<div class="state-message is-loading">Loading player&hellip;</div>`;
      if (!DETAIL_LOADING) {
        DETAIL_LOADING = true;
        fetch("/data/mlb_player_detail.json", { cache: "no-cache" })
          .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
          .then(d => { DETAIL = d; if (state.player) renderPlayer(state.player); })
          .catch(() => {
            DETAIL_LOADING = false;
            root.innerHTML = `<div class="state-message is-error" role="alert">Data failed to load. Refresh to retry; if it persists the nightly build is mid-run. <button class="chip" id="mlbp-detail-retry" type="button">Retry</button></div>`;
            const retry = document.getElementById("mlbp-detail-retry");
            if (retry) retry.onclick = () => { if (state.player) renderPlayer(state.player); };
          });
      }
      return;
    }
    const p = (DETAIL.players || {})[key];
    if (!p) {
      root.innerHTML = `<div class="state-message">No detail for "${esc(key)}". <a href="#" onclick="location.hash='';return false;">Back</a>.</div>`;
      return;
    }
    ensureFielding(key);
    if (!p.isPit || p.twoWay) ensureSwingDelta(key);
    // Only client-fetch the pitching leaderboards when the skills block was not
    // baked into the payload (older builds); the baked block renders directly.
    if ((p.isPit || p.twoWay) && !(p.skills && p.skills.pitch)) ensurePitchingStats(key);
    const photo = p.mlbam
      ? `<img class="mlbp-headshot" src="${headshotURL(p.mlbam, 240)}" alt="" onerror="this.style.visibility='hidden'">` : "";
    const tiles = [];
    const tile = (label, val, cls, title) => tiles.push(`<div class="mlbp-tile"${title ? ` title="${esc(title)}"` : ""}><span class="mlbp-tile-label">${label}</span><span class="mlbp-tile-val ${cls || ""}">${val}</span></div>`);
    if (p.proj && p.proj.warTotal != null)
      // Total-WAR band dropped (F-01, miscalibrated); per-year bands stay in the fan chart + upside strip.
      tile(`${(p.proj.war || []).length}y WAR`, `${fmtWar(p.proj.warTotal)}`,
        null, "Expected (attrition-discounted) bWAR over the projection window - the same path surplus prices. The board headline uses the if-healthy path, which reads a little higher.");
    if (p.proj && surOf(p.proj) != null) {
      const _pv = surOf(p.proj);
      // Name the basis when the only priced months are the rest of this season,
      // so a small honest number does not read as a broken one.
      const _lbl = (p.proj.surNpv == null && p.proj.surRos != null) ? "Surplus (rest of season)" : "Surplus NPV";
      tile(_lbl, money(_pv), _pv >= 0 ? "proj-pos" : "proj-neg");
    }
    // HEM+ (hitters): pure offensive-rate skill from the MLB Stats leaderboards.
    if (p.skills && p.skills.hem && p.skills.hem.hemPlus != null) {
      const h = p.skills.hem;
      tile("HEM+", `${h.hemPlus}${h.hemPlus3yr != null ? `<span class="fa-band"> 3yr ${h.hemPlus3yr}</span>` : ""}`,
        h.hemPlus >= 112 ? "proj-pos" : h.hemPlus <= 88 ? "proj-neg" : "",
        "HEM+: a hitter's pure offensive-rate skill (100 = average qualified hitter), a sample-shrunk wOBA. From the MLB Stats hitter leaderboards.");
      // xHEM+ and the luck gap: what the batted-ball inputs say he should have hit.
      if (h.xhemPlus != null)
        tile("xHEM+", `${h.xhemPlus}${h.luckGap != null ? `<span class="fa-band"> luck ${h.luckGap > 0 ? "+" : ""}${h.luckGap}</span>` : ""}`,
          h.xhemPlus >= 112 ? "proj-pos" : h.xhemPlus <= 88 ? "proj-neg" : "",
          "xHEM+ is HEM+ rebuilt on expected (batted-ball) inputs instead of outcomes. The luck gap is HEM+ minus xHEM+: positive means results have run ahead of the contact quality behind them.");
      // WAR/PA+ is 100 + 10z, so it bands at 80/120 (two pool sigma), NOT at the
      // wRC+-width 88/112 the HEM+ family above uses. Do not "tidy" these to match:
      // a 112 here is 1.2 sigma, which is a genuinely good hitter, not an average one.
      if (h.warPaPlus != null)
        tile("WAR/PA+", `${h.warPaPlus}${h.warPaPlusPct != null ? `<span class="fa-band"> p${h.warPaPlusPct}</span>` : ""}`,
          h.warPaPlus >= 120 ? "proj-pos" : h.warPaPlus <= 80 ? "proj-neg" : "",
          "Batting bWAR per plate appearance, indexed so 100 is average and every TEN points is one standard deviation of the hitter pool. That is a wider ruler than HEM+: a 113 is the 91st percentile, not 13 percent above average. Carries fielding, baserunning and the positional adjustment, which HEM+ leaves out. The p-number is the percentile.");
      if (h.warPaPlusAdj != null)
        tile("WAR/PA+ adj", `${h.warPaPlusAdj}`,
          h.warPaPlusAdj >= 120 ? "proj-pos" : h.warPaPlusAdj <= 80 ? "proj-neg" : "",
          "The same index with the rate regressed toward league average by playing time, so a hot short sample does not outrank a full season. A readability aid, not a forecast: neither WAR rate predicts next season better than plain season bWAR.");
    }
    if (p.swingPlus != null) tile("Swing+", `${p.swingPlus}<span class="fa-band"> n=${p.swingN}</span>`, p.swingPlus >= 105 ? "proj-pos" : p.swingPlus <= 95 ? "proj-neg" : "");
    // W6 display-only: per-season Swing+ trend. swingPlusSeasons rides the
    // detail payload where scored; the guard covers older payloads and
    // one-season hitters. * marks a sub-180-swing season (partial tracking,
    // shrunk hard toward 100 by the model's reliability weight).
    if (p.swingPlusSeasons) {
      const sy = Object.keys(p.swingPlusSeasons).filter(y => (p.swingPlusSeasons[y] || {}).swing_plus != null).sort();
      if (sy.length >= 2) {
        const seg = sy.map(y => `${y.slice(2)}: ${Math.round(p.swingPlusSeasons[y].swing_plus)}${p.swingPlusSeasons[y].low_n ? "*" : ""}`).join(" / ");
        const sd = p.swingPlusSeasons[sy[sy.length - 1]].swing_plus - p.swingPlusSeasons[sy[sy.length - 2]].swing_plus;
        tile("Swing+ trend", `<span class="mlbp-swing-seasons">${seg}</span>`,
          sd >= 5 ? "proj-pos" : sd <= -5 ? "proj-neg" : "",
          "Per-season Swing+ (Will Cahoon's model): the same competitive-swing filter and 360-swing reliability shrink, scored season by season. * = under 180 swings that season. Display context only - the pooled Swing+ tile is the served number.");
      }
    }
    if (p.aaaStuffPlus != null) tile("aStuff+", `${Math.round(p.aaaStuffPlus)}<span class="fa-band"> AAA ${p.aaaStuffSeason}</span>`, p.aaaStuffPlus >= 110 ? "proj-pos" : p.aaaStuffPlus <= 90 ? "proj-neg" : "");
    if (p.fa && p.fa.projAav != null) tile("Proj AAV", money(p.fa.projAav));
    // Two-way: surface the hitting vs pitching WAR split (the path above sums both).
    if (p.twoWay && p.proj && p.proj.warHit)
      tile("Hitting WAR", fmtWar((p.proj.warHit || []).reduce((a, b) => a + b, 0)), null,
        "Projected bWAR from the hitting side over the window (the headline path sums both sides).");
    if (p.twoWay && p.proj && p.proj.warPit)
      tile("Pitching WAR", fmtWar((p.proj.warPit || []).reduce((a, b) => a + b, 0)), null,
        "Projected bWAR from the pitching side over the window (the headline path sums both sides).");
    const contract = p.proj && p.proj.thru
      ? `signed thru ${p.proj.thru}${p.proj.aav ? ` · ${money(p.proj.aav)}/y` : ""}`
      : (p.fa ? `free agent${p.fa.type ? ` · ${esc(p.fa.type)}` : ""}` : "arb / pre-arb");
    // Prospect origin line (ex-PROSPX players): the FV arc endpoints +
    // debut date - the hub strip carries the link to the full arc.
    const org = p.origin;
    const originLine = (org && org.prospx)
      ? `<div class="fa-sub mlbp-origin-line"><a class="fa-player-link" href="/prospx/#player=${encodeURIComponent(org.prospx)}" title="Open this player's full PROSPX prospect page (FV history, tools, eFV)">ex-PROSPX prospect &rarr;</a>${org.fvOpen != null && org.fvClose != null ? ` · FV ${org.fvOpen} &rarr; ${org.fvClose}` : ""}${org.debut ? ` · debuted ${esc(org.debut)}` : ""}${fvSparkSVG(org.fvSpark)}</div>`
      : "";
    root.innerHTML = `<div class="mlbp-page">
      <div id="mlbp-hub"></div>
      <div class="mlbp-hero">
        ${photo}
        <div class="mlbp-hero-main">
          <div class="mlbp-name">${teamLogo(p.team)}<h2>${esc(p.name || key)}</h2></div>
          <div class="fa-sub">${esc(p.pos || "")}${p.age != null ? ` · age ${Math.floor(p.age)}` : ""}${p.team ? ` · ${esc(p.team)}` : " · FA"} · ${contract}</div>
          ${originLine}
          <div class="mlbp-hero-actions"><button class="chip egfx-chip" id="mlbp-gfx" title="Generate a shareable graphic (theme-aware)"><span class="egfx-chip-glyph" aria-hidden="true">&#9636;</span>Generate GFX</button>${(p.proj && surOf(p.proj) != null) ? `<a class="chip" href="/trademachine/#tm=mlb:${encodeURIComponent(key)}" title="Value this player in the Trade Machine - prospects (eFV surplus) and MLB players (projection surplus) on one currency">&#8646; Trade Machine</a>` : ""}</div>
        </div>
        <div class="mlbp-tiles">${tiles.join("")}</div>
      </div>
      ${batSpeedChip(p)}
      ${mlbpTabs(p, key)}
      <div class="fa-note mlbp-page-foot">Projections: the eephus projection engine (proj_lgbm_v1; bands = empirical residual quantiles). Statcast percentiles vs the season's qualified MLB pool. ${p.swingPlus != null ? "Swing+ by Will Cahoon (MLB bat tracking 2024+)." : ""}${p.swingPlusSeasons ? " Swing+ trend is per-season with the same reliability shrink; * = under 180 swings that season." : ""}${p.aaaStuffPlus != null ? " aStuff+: in-house AAA pitch-quality model (per-pitch kinematics vs run value, latest tracked AAA season)." : ""}</div>
    </div>`;
    bindMlbpTabs(root, p, key);
    // hub strip (cross-module identity) - lazy, never blocks the paint
    if (window.EEPHUS_HUB) {
      window.EEPHUS_HUB.links().then(L => {
        const row = L && (L.byKey || {})[key];
        const el = document.getElementById("mlbp-hub");
        if (el && row) el.innerHTML = window.EEPHUS_HUB.stripHTML(row, "mlb");
      });
      const btn = document.getElementById("mlbp-gfx");
      if (btn) btn.onclick = () => shareMlbCard(p);
    }
  }

  // One-subject card exports go through EEPHUS_HUB.openCard (the shared
  // wrapper - DE-DUP 2026-07-23; it prefers the GFX modal, falls back to the
  // direct shareCard download).

  // Board spec for the Generate GFX modal: the league projection board as a
  // column leaderboard (projected 5y bWAR, P10-P90 range, contract surplus).
  function _projBoardSpec(top) {
    // Same HORIZON-windowed total the on-site board shows and sorts by
    // (warShown), so the shared graphic never disagrees with the board row.
    const war = m => warShown(m);
    // A late-ETA prospect's exported P10/P90 totals bracket the ETA-anchored
    // FULL-window total, not the calendar-windowed point above - drop the
    // range for those rows rather than print a band around the wrong number.
    const clipped = m => m.src === "prospect" && m.eta > DATA.first_season;
    const lo = m => clipped(m) ? null : (m.warTotalPTHP10 != null ? m.warTotalPTHP10 : m.warTotalP10);
    const hi = m => clipped(m) ? null : (m.warTotalPTHP90 != null ? m.warTotalPTHP90 : m.warTotalP90);
    const rows = top.map((m, i) => {
      const cells = [
        { t: i + 1 },
        { t: m.name, sub: [m.pos, m.team].filter(Boolean).join(" · ") || undefined },
        { t: war(m) != null ? fmtWar(war(m)) : "-", c: "accent" },
        { t: lo(m) != null ? `${fmtWar(lo(m))}-${fmtWar(hi(m))}` : "-", c: "muted" },
      ];
      const s = (surOf(m) != null) ? surOf(m) : (m.surplus != null ? m.surplus : null);
      cells.push(s != null ? { t: money(s), c: s >= 0 ? "pos" : "neg" } : { t: "-" });
      return { cells };
    });
    return {
      kind: "board", module: "MLB Projections", accentToken: "--accent-cyan",
      title: "MLB Projections · Five-Year bWAR Leaders",
      subtitle: `${DATA.n_vets} veterans + ${DATA.n_prospects} prospects · seasons ${DATA.first_season}-${DATA.first_season + DATA.horizon - 1}`,
      url: "eephus.io/projections", filenameBase: "eephus-projections-board",
      caption: "Gate-validated engine · floor / mean / ceiling buckets · prospects join at their PROSPX ETA",
      board: { defaultCount: 25, counts: [10, 25, 50], columns: [
        { label: "#", frac: 0.05 },
        { label: "Player", frac: 0.40 },
        { label: "Proj 5y WAR", frac: 0.16 },
        { label: "Range P10-P90", frac: 0.22, wideOnly: true },
        { label: "Surplus", frac: 0.15, wideOnly: true },
      ], rows },
    };
  }

  // Board spec for the Generate GFX modal when the Team Outlook tab is active,
  // so the graphic tracks the menu you're viewing (the Players tab exports
  // _projBoardSpec; this exports the team roll-up board instead).
  function _teamOutlookBoardSpec(rows) {
    const hasFarm = rows.some(r => r.farm);
    const hasControl = rows.some(r => r.lockedPct != null);
    const brows = rows.map((r, i) => {
      const f = r.farm || {};
      const w = Math.round(r.wins);
      const cells = [
        { t: i + 1 },
        { t: r.team },
        { t: r.war != null ? r.war.toFixed(1) : "-", c: "accent" },
        { t: `${w}-${162 - w}` },
      ];
      if (hasControl) {
        const pct = r.lockedPct != null ? Math.round(r.lockedPct * 100) : null;
        const cell = { t: pct == null ? "-" : `${pct}%` };
        if (pct != null) { if (pct >= 75) cell.c = "pos"; else if (pct <= 45) cell.c = "neg"; }
        cells.push(cell);
      }
      cells.push(f.farmRank != null ? { t: `#${f.farmRank}` } : { t: "-" });
      cells.push(f.farmSurplusMM != null
        ? { t: `$${Math.round(f.farmSurplusMM)}M`, c: f.farmSurplusMM >= 0 ? "pos" : "neg" }
        : { t: "-" });
      return { cells };
    });
    const cols = [
      { label: "#", frac: 0.06 },
      { label: "Team", frac: hasControl ? 0.26 : 0.30 },
      { label: "Roster WAR", frac: 0.16 },
      { label: "Proj W-L", frac: 0.16 },
    ];
    if (hasControl) cols.push({ label: "Core control", frac: 0.14 });
    cols.push({ label: "Farm", frac: 0.11, wideOnly: true });
    cols.push({ label: "Farm surplus", frac: 0.13, wideOnly: true });
    return {
      kind: "board", module: "MLB Projections", accentToken: "--accent-cyan",
      title: "MLB Projections · Team Outlook",
      subtitle: `${DATA.first_season} roster bWAR → projected wins${hasControl ? " · core control" : ""} · ${rows.length} teams`,
      url: "eephus.io/projections", filenameBase: "eephus-projections-team-outlook",
      caption: "Roster WAR at the 47.7 replacement baseline · league-recentered"
        + (hasControl ? " · core control = cost-controlled WAR locked up for the future" : "")
        + (hasFarm ? " · farm rank + surplus from the PROSPX org models" : ""),
      board: { defaultCount: 30, counts: [10, 30], columns: cols, rows: brows },
    };
  }

  // Unified share card - declarative since GFX slice 4: this builder now only
  // maps the detail payload's DATA (display-formatted with this module's own
  // fmtWar/money rules) onto the shared "player-projection" template;
  // EEPHUS_HUB.templates owns the tile/section layout. Data priorities are
  // unchanged: projection band + surplus + Swing+ up top, Statcast
  // percentiles and (pitchers) arsenal as the body sections.
  function shareMlbCard(p) {
    const first = DATA.first_season;
    const war = (p.proj && p.proj.war) || [];
    window.EEPHUS_HUB.openCard({
      template: "player-projection",
      data: {
        warYears: war.length,
        warTotal: (p.proj && p.proj.warTotal != null) ? fmtWar(p.proj.warTotal) : null,
        surplus: (p.proj && surOf(p.proj) != null)
          ? { value: money(surOf(p.proj)), neg: !(surOf(p.proj) >= 0) } : null,
        swingPlus: p.swingPlus != null ? String(Math.round(p.swingPlus)) : null,
        aaaStuffPlus: p.aaaStuffPlus != null ? String(Math.round(p.aaaStuffPlus)) : null,
        projAav: (p.fa && p.fa.projAav != null) ? money(p.fa.projAav) : null,
        firstSeason: first,
        lastSeason: first + (war.length - 1),
        warRows: war.map((w, t) => ({ season: String(first + t), war: fmtWar(w),
          band: (p.proj.warP10 || [])[t] != null
            ? `${fmtWar(p.proj.warP10[t])}-${fmtWar(p.proj.warP90[t])}` : null })),
        // arsenal is pitcher-gated HERE (not in the template) so a stray
        // arsenal field on a hitter payload still falls through to Statcast,
        // exactly like the pre-template builder.
        arsenal: (p.isPit && p.arsenal) ? p.arsenal.map(a => ({ pitch: a.pitch || "?",
          usageWhiff: `${a.usage != null ? a.usage.toFixed(0) + "%" : "-"} / ${a.whiff != null ? a.whiff.toFixed(0) + "%" : "-"}` })) : [],
        statcast: (p.sc && p.sc.metrics && p.sc.metrics.length)
          ? { season: p.sc.season, metrics: p.sc.metrics } : null,
      },
      module: "MLB Projections",
      accentToken: "--accent-cyan",
      name: p.name || p.key,
      meta: `${p.pos || ""}${p.age != null ? ` · age ${Math.floor(p.age)}` : ""}${p.team ? ` · ${p.team}` : " · FA"}`,
      sub: p.fa && p.fa.verdict ? `FA verdict: ${String(p.fa.verdict).toUpperCase()}` : "",
      headshotURL: p.mlbam ? headshotURL(p.mlbam, 240) : null,
      url: `eephus.io/projections/#player=${p.key}`,
      filename: `eephus-${p.key}-mlb-card.png`,
      caption: "eephus projection engine (proj_lgbm_v1) · bands = P10-P90 · Statcast percentiles vs qualified MLB pool",
    });
  }

  // Board payload loader, split out of boot() so the error-state Retry button
  // can re-fetch without stacking a second hashchange listener.
  function loadData() {
    const root = document.getElementById("proj-rows");
    if (!root) return;
    root.innerHTML = `<div class="state-message is-loading">Loading projections&hellip;</div>`;
    fetch("/data/mlb_projections.json", { cache: "no-cache" })
      .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
      .then(d => { DATA = d; render(); })
      .catch(() => {
        root.innerHTML = `<div class="state-message is-error" role="alert">Data failed to load. Refresh to retry; if it persists the nightly build is mid-run. <button class="chip" id="proj-retry" type="button">Retry</button></div>`;
        const retry = document.getElementById("proj-retry");
        if (retry) retry.onclick = loadData;
      });
  }

  function boot() {
    syncFromURL();
    if (!document.getElementById("proj-rows")) return;
    loadData();
    window.addEventListener("hashchange", () => { syncFromURL(); render(); });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
