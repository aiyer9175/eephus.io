const CSV_PATH = "b1g_2025_hitter_xwoba_min30pa.csv";

// Real school names for team codes (owner ask 2026-06-12: badges read
// "Minnesota", never "MIN_GOL"). Unknown codes fall back to a cleaned slug.
// formatTeamName + the full national school-code dicts now live in the shared
// collegesavant/team_names.js (loaded before this file on the hitter page), so
// the 3,600-row national set resolves real school names instead of raw codes.

// `gl` is the data/glossary.json slug for this metric, when one exists; it wires
// the same site-wide hover tooltip the rest of eephus uses. Metrics with no slug
// yet (xwOBA, the zone/contact family) stay plain until their entries land.
const METRICS = [
  { key: "xwoba", label: "xwOBA", fmt: "decimal", higherBetter: true },
  { key: "average_exit_velocity", label: "Avg EV", fmt: "mph", higherBetter: true, gl: "exit_velocity" },
  { key: "90th_percentile_exit_velocity", label: "90th EV", fmt: "mph", higherBetter: true, gl: "exit_velocity" },
  { key: "max_exit_velocity", label: "Max EV", fmt: "mph", higherBetter: true, gl: "exit_velocity" },
  { key: "swing_pct", label: "Swing %", fmt: "pct", higherBetter: true },
  { key: "chase_pct", label: "Chase %", fmt: "pct", higherBetter: false, gl: "chase_pct" },
  { key: "whiff_pct", label: "Whiff %", fmt: "pct", higherBetter: false, gl: "whiff_pct" },
  { key: "zone_swing_pct", label: "Zone Swing %", fmt: "pct", higherBetter: true },
  { key: "zone_contact_pct", label: "Zone Contact %", fmt: "pct", higherBetter: true },
  { key: "o_contact_pct", label: "O-Contact %", fmt: "pct", higherBetter: true },
  { key: "sweet_spot_pct", label: "Sweet Spot %", fmt: "pct", higherBetter: true },
  { key: "barrel_pct", label: "Barrel %", fmt: "pct", higherBetter: true, gl: "barrel_pct" },
  { key: "hard_hit_pct", label: "Hard-Hit %", fmt: "pct", higherBetter: true, gl: "hard_hit_pct" },
  { key: "k_pct", label: "K %", fmt: "pct", higherBetter: false, gl: "k_pct" },
  { key: "bb_pct", label: "BB %", fmt: "pct", higherBetter: true, gl: "bb_pct" },
  { key: "k_minus_bb_pct", label: "K-BB %", fmt: "pct", higherBetter: false, gl: "k_bb_pct" },
];

// Render a metric's label, wrapped in a glossary term span when the site
// glossary defines it (EEPHUS_GL.wire then attaches the tooltip). Returns
// escaped plain text otherwise. HTML-safe; callers must NOT re-escape.
function glLabel(metric) {
  const text = escapeHtml(metric ? metric.label : "");
  return metric && metric.gl ? `<span class="g-term" data-gl="${metric.gl}">${text}</span>` : text;
}

const TEAM_LOGOS = {
  ILL_ILL: "logos/ILL_ILL.png",
  IU: "logos/IU.png",
  IOW_HAW: "logos/IOW_HAW.png",
  MAR_TER: "logos/MAR_TER.png",
  MIC_SPA: "logos/MIC_SPA.png",
  MIC_WOL: "logos/MIC_WOL.png",
  MIN_GOL: "logos/MIN_GOL.png",
  NEB: "logos/NEB.png",
  NOR_CAT: "logos/NOR_CAT.png",
  ORE_DUC: "logos/ORE_DUC.png",
  OSU_BUC: "logos/OSU_BUC.png",
  PEN_NIT: "logos/PEN_NIT.png",
  PUR_BOI: "logos/PUR_BOI.png",
  RUT_SCA: "logos/RUT_SCA.png",
  SOU_TRO: "logos/SOU_TRO.png",
  WAS_HUS: "logos/WAS_HUS.png",
};

const HOME_WIDGET_METRICS = [
  { key: "cs_plus", label: "CS+ (pro profile)" },
  { key: "average_exit_velocity", label: "EV" },
  { key: "90th_percentile_exit_velocity", label: "90th Percentile EV" },
  { key: "zone_contact_pct", label: "Z Contact" },
  { key: "hard_hit_pct", label: "Hard-Hit %" },
  { key: "whiff_pct", label: "Whiff %" },
  { key: "k_minus_bb_pct", label: "K-BB %" },
];

// Section hub on the home page: orient the reader to every CollegeSavant view
// instead of dropping them straight into one dashboard.
const HOME_SECTIONS = [
  { route: "leaders", title: "Hitter Leaderboard", note: "Every tracked hitter, sortable across EV, discipline, and CS+, with team and qualified-PA filters." },
  { route: "teams", title: "Team Tendencies", note: "Which college programs hit the ball hardest, chase the least, and run the best team CS+." },
  { route: "prospects", title: "Draft Prospects", note: "Draft-eligible college hitters carried in by the box scores we hold, FV-ranked with a projected Single-A line." },
  { route: "projections", title: "MiLB Projections", note: "Each hitter's projected Single-A line, the matched-pair method, and its leave-one-out backtest." },
];

const LEADERBOARD_LIMIT = 300;

const state = {
  allPlayers: [],
  players: [],
  availableYears: [],
  year: 2025,
  sortKey: "xwoba",
  query: "",
  percentiles: new Map(),
  battedBalls: new Map(),
};

const app = document.querySelector("#app");

// ---- CS+ : the college tracked-skill index, in the eephus "+" family --------
// A pool-anchored z-average of the tracked skills, rescaled to 100 + 10*z, the
// SAME convention as PROSPX SC+ (100 = cohort average, +10 = one standard
// deviation better). Two equally-weighted skill families so neither outvotes
// the other by carrying more components. This is a COLLEGE-RELATIVE index (vs
// the same per-year pool the sliders use), NOT a Single-A projection.
// Declared before init() runs so computeCSPlus never hits the const's dead zone.
const CSPLUS_GROUPS = [
  { name: "contact quality", parts: [
    { key: "90th_percentile_exit_velocity", dir: 1 },
    { key: "barrel_pct", dir: 1 },
    { key: "hard_hit_pct", dir: 1 },
  ] },
  { name: "plate discipline", parts: [
    { key: "zone_contact_pct", dir: 1 },
    { key: "whiff_pct", dir: -1 },
    { key: "chase_pct", dir: -1 },
  ] },
];

function meanStd(values) {
  const v = values.filter(Number.isFinite);
  if (!v.length) return [0, 1];
  const m = v.reduce((a, b) => a + b, 0) / v.length;
  const sd = Math.sqrt(v.reduce((a, b) => a + (b - m) * (b - m), 0) / v.length);
  return [m, sd || 1];
}

function computeCSPlus(players) {
  const stats = {};
  for (const group of CSPLUS_GROUPS) {
    for (const part of group.parts) {
      if (!stats[part.key]) stats[part.key] = meanStd(players.map((p) => p[part.key]));
    }
  }
  const out = new Map();
  for (const player of players) {
    const groupZ = [];
    for (const group of CSPLUS_GROUPS) {
      const zs = [];
      for (const part of group.parts) {
        const value = player[part.key];
        if (!Number.isFinite(value)) continue;
        const [m, sd] = stats[part.key];
        zs.push(part.dir * (value - m) / sd);
      }
      if (zs.length) groupZ.push(zs.reduce((a, b) => a + b, 0) / zs.length);
    }
    if (!groupZ.length) { out.set(player.slug, null); continue; }
    const avgZ = groupZ.reduce((a, b) => a + b, 0) / groupZ.length;
    out.set(player.slug, Math.round(Math.max(40, Math.min(160, 100 + 10 * avgZ))));
  }
  return out;
}

// Pill markup for a "+" index (CS+ or a component), matching the site is-pos /
// is-neg thresholds (>=110 good, <=90 below). Returns "" for a missing value.
function plusPill(value, label) {
  if (!Number.isFinite(value)) return "";
  const cls = value >= 110 ? "is-pos" : value <= 90 ? "is-neg" : "";
  const tip = `${label} ${value} - tracked-skill index, 100 = ${state.year} college average, +10 = one standard deviation better. College-relative, not a Single-A projection.`;
  return `<span class="cs-plus-pill ${cls}" title="${escapeHtml(tip)}">${escapeHtml(label)} ${value}</span>`;
}

init();

async function init() {
  try {
    if (window.HITTER_DATA) {
      state.allPlayers = window.HITTER_DATA.map(normalizePlayer);
      state.battedBalls = normalizeBattedBalls(window.HITTER_BIP || {});
    } else {
      const text = window.B1G_CSV || await fetch(CSV_PATH).then((res) => {
        if (!res.ok) throw new Error(`Could not load ${CSV_PATH}`);
        return res.text();
      });
      state.allPlayers = parseCsv(text).map((row) => normalizePlayer({ ...row, year: 2025 }));
      state.battedBalls = normalizeBattedBalls(window.B1G_BIP || {});
    }
    state.availableYears = [...new Set(state.allPlayers.map((player) => player.year))].sort((a, b) => b - a);
    state.year = state.availableYears[0] || 2025;
    setActiveYear(yearFromHash(window.location.hash) || state.year);
    window.addEventListener("hashchange", render);
    render();
  } catch (error) {
    app.innerHTML = `<section class="empty"><strong>Could not load hitter data.</strong><br>${escapeHtml(error.message)}</section>`;
  }
}

function normalizeBattedBalls(raw) {
  const bySlug = new Map();
  for (const [slug, points] of Object.entries(raw)) {
    bySlug.set(slug, points.map((point) => ({
      ev: Number(point.ev),
      la: Number(point.la),
      barrel: Boolean(point.barrel),
      hard: Boolean(point.hard),
    })));
  }
  return bySlug;
}

function parseCsv(text) {
  const rows = [];
  let row = [];
  let value = "";
  let quoted = false;

  for (let i = 0; i < text.length; i += 1) {
    const char = text[i];
    const next = text[i + 1];

    if (char === '"' && quoted && next === '"') {
      value += '"';
      i += 1;
    } else if (char === '"') {
      quoted = !quoted;
    } else if (char === "," && !quoted) {
      row.push(value);
      value = "";
    } else if ((char === "\n" || char === "\r") && !quoted) {
      if (char === "\r" && next === "\n") i += 1;
      row.push(value);
      if (row.some((cell) => cell.length)) rows.push(row);
      row = [];
      value = "";
    } else {
      value += char;
    }
  }

  if (value.length || row.length) {
    row.push(value);
    rows.push(row);
  }

  const [headers, ...body] = rows;
  return body.map((cells) =>
    Object.fromEntries(headers.map((header, index) => [header, cells[index] ?? ""]))
  );
}

function normalizePlayer(row) {
  const player = { ...row };
  for (const metric of METRICS) {
    const raw = row[metric.key];
    player[metric.key] = raw === "" ? null : Number(raw);
  }
  if (!Number.isFinite(player.k_minus_bb_pct)) {
    player.k_minus_bb_pct = Number.isFinite(player.bb_pct) && Number.isFinite(player.k_pct)
      ? player.k_pct - player.bb_pct
      : null;
  }
  player.year = Number(row.year || 2025);
  player.slug = slugify(player.hitter_name);
  player.team = row.team || window.B1G_TEAMS?.[player.slug]?.team || "";
  player.teamLabel = row.team || window.B1G_TEAMS?.[player.slug]?.label || player.team;
  player.teamClass = player.team ? `team-${slugify(player.team)}` : "team-unknown";
  player.initials = player.hitter_name
    .split(/[,\s]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0])
    .join("")
    .toUpperCase();
  return player;
}

function setActiveYear(year) {
  const numericYear = Number(year);
  state.year = state.availableYears.includes(numericYear) ? numericYear : (state.availableYears[0] || numericYear);
  state.players = state.allPlayers.filter((player) => player.year === state.year);
  state.percentiles = computePercentiles(state.players);
  state.csPlus = computeCSPlus(state.players);
}

function yearFromHash(hash) {
  const playerMatch = String(hash || "").match(/^#\/player\/(\d{4})\//);
  if (playerMatch) return Number(playerMatch[1]);
  const leaderMatch = String(hash || "").match(/^#\/leaders\/[^/]+\/(\d{4})$/);
  if (leaderMatch) return Number(leaderMatch[1]);
  return null;
}

function computePercentiles(players) {
  const byPlayer = new Map();
  const pools = new Map();

  for (const metric of METRICS) {
    pools.set(metric.key, players
      .map((p) => p[metric.key])
      .filter((value) => Number.isFinite(value))
      .sort((a, b) => a - b));
  }

  for (const player of players) {
    const values = {};
    for (const metric of METRICS) {
      const pool = pools.get(metric.key) || [];
      const value = player[metric.key];
      if (!Number.isFinite(value) || pool.length < 2) {
        values[metric.key] = null;
        continue;
      }

      let percentile = percentileFromPool(pool, value);
      if (!metric.higherBetter) percentile = 100 - percentile;
      values[metric.key] = Math.max(1, Math.min(99, percentile));
    }
    byPlayer.set(player.slug, values);
  }

  return byPlayer;
}

function percentileFromPool(pool, value) {
  const less = lowerBound(pool, value);
  const equal = upperBound(pool, value) - less;
  return Math.round(((less + 0.5 * equal) / pool.length) * 100);
}

function lowerBound(values, target) {
  let low = 0;
  let high = values.length;
  while (low < high) {
    const mid = (low + high) >> 1;
    if (values[mid] < target) low = mid + 1;
    else high = mid;
  }
  return low;
}

function upperBound(values, target) {
  let low = 0;
  let high = values.length;
  while (low < high) {
    const mid = (low + high) >> 1;
    if (values[mid] <= target) low = mid + 1;
    else high = mid;
  }
  return low;
}

function render() {
  const hash = window.location.hash || "#/";
  const requestedYear = yearFromHash(hash);
  if (requestedYear && requestedYear !== state.year) setActiveYear(requestedYear);
  updateNav(hash);

  if (hash.startsWith("#/player/")) {
    const parts = hash.replace("#/player/", "").split("/");
    const slug = parts.length > 1 ? parts.slice(1).join("/") : parts[0];
    const player = state.players.find((p) => p.slug === slug);
    renderPlayer(player);
    afterRender();
    return;
  }

  if (hash.startsWith("#/leaders/")) {
    const key = hash.replace("#/leaders/", "").split("/")[0];
    if (key === "cs_plus" || METRICS.some((metric) => metric.key === key)) state.sortKey = key;
    renderLeaderboard();
    afterRender();
    return;
  }

  if (hash.startsWith("#/teams")) {
    renderTeams();
    afterRender();
    return;
  }

  if (hash.startsWith("#/projections")) {
    renderProjections();
    afterRender();
    return;
  }

  if (hash.startsWith("#/prospects")) {
    renderProspects();
    afterRender();
    return;
  }

  renderHome();
  afterRender();
}

// Post-render hooks shared by every view. Lights up the site glossary tooltips
// on any [data-gl] term spans the view emitted (no-op if eephus-gl.js absent).
function afterRender() {
  if (window.EEPHUS_GL && window.EEPHUS_GL.wire) window.EEPHUS_GL.wire(app);
}

function updateNav(hash) {
  document.querySelectorAll("[data-route]").forEach((link) => {
    const route = link.getAttribute("href");
    const section = hash.startsWith("#/teams") ? "#/teams"
      : hash.startsWith("#/projections") ? "#/projections"
      : hash.startsWith("#/prospects") ? "#/prospects" : "#/";
    link.classList.toggle("is-active", route === section);
  });
  // The hitters/pitchers toggle lands you on the same section on the other side
  // (Team Tendencies -> Team Tendencies, Pro Projections -> Pro Projections),
  // not always the other page's home. Player/leaderboard views do not cross, so
  // they fall back to home.
  const cross = document.querySelector("[data-cross-page]");
  if (cross) {
    const base = cross.getAttribute("data-cross-page");
    const section = hash.startsWith("#/teams") ? "#/teams"
      : hash.startsWith("#/projections") ? "#/projections" : "#/";
    cross.setAttribute("href", base + section);
  }
}

function renderHome() {
  const hub = HOME_SECTIONS.map((s) => {
    const href = s.route === "leaders" ? `#/leaders/cs_plus/${state.year}` : `#/${s.route}`;
    return `<a class="hub-card" href="${href}">
      <strong>${s.title}</strong>
      <span class="hub-note">${s.note}</span>
      <span class="hub-go">Open</span>
    </a>`;
  }).join("");
  app.innerHTML = `
    <section class="toolbar home-toolbar">${renderYearSelect()}</section>

    <section class="home-intro">
      <h1>CollegeSavant - Hitters</h1>
      <p>Tracked batted-ball quality and plate discipline, a pool-anchored CS+ index, and a college-to-Single-A projection for the ${state.year} college dataset.</p>
    </section>

    <section class="hub-grid">${hub}</section>

    <div class="panel-title" style="margin-top:20px;"><span>Top of the ${state.year} class</span><span>leaders by the metrics that travel to pro ball</span></div>
    <section class="widget-grid">
      ${HOME_WIDGET_METRICS.map((item) => renderTopWidget({ ...getMetric(item.key), label: item.label })).join("")}
    </section>
  `;

  const yearSelect = app.querySelector(".year-select");
  if (yearSelect) {
    yearSelect.addEventListener("change", (event) => {
      setActiveYear(event.target.value);
      window.location.hash = "#/";
      renderHome();
    });
  }
}

function renderTopWidget(metric) {
  const rows = topRowsForMetric(metric).slice(0, 10);
  return `
    <article class="top-widget">
      <div class="widget-title">
        <span>${glLabel(metric)}</span>
        <a href="#/leaders/${metric.key}/${state.year}">View All</a>
      </div>
      <div class="widget-list">
        ${rows.map((player, index) => `
          <a class="widget-row" href="#/player/${player.year}/${player.slug}">
            <span class="widget-rank">${index + 1}</span>
            <span class="widget-name">${escapeHtml(displayName(player.hitter_name))}</span>
            <span class="widget-team">${TEAM_LOGOS[player.team] ? `<img class="widget-logo" src="${TEAM_LOGOS[player.team]}" alt="" loading="lazy" onerror="this.remove()">` : ""}${escapeHtml(formatTeamName(player.team))}</span>
            <strong>${metric.key === "cs_plus" ? Math.round(state.csPlus && state.csPlus.get(player.slug)) : formatMetric(player[metric.key], metric.fmt)}</strong>
          </a>
        `).join("")}
      </div>
    </article>
  `;
}

function topRowsForMetric(metric) {
  const direction = metric.higherBetter ? -1 : 1;
  if (metric.key === "cs_plus") {
    return state.players
      .filter((player) => Number.isFinite(state.csPlus && state.csPlus.get(player.slug)))
      .sort((a, b) => state.csPlus.get(b.slug) - state.csPlus.get(a.slug));
  }
  return state.players
    .filter((player) => Number.isFinite(player[metric.key]))
    .sort((a, b) => direction * compareNullable(a[metric.key], b[metric.key]));
}

// Sortable stat columns on the hitter leaderboard. higherBetter sets the natural
// sort direction the first time you click a column; clicking it again toggles.
const LB_COLUMNS = [
  { key: "cs_plus", label: "CS+", fmt: "plus", higherBetter: true },
  { key: "xwoba", label: "xwOBA", fmt: "dec", higherBetter: true },
  { key: "average_exit_velocity", label: "Avg EV", fmt: "mph", higherBetter: true, gl: "exit_velocity" },
  { key: "90th_percentile_exit_velocity", label: "90th EV", fmt: "mph", higherBetter: true, gl: "exit_velocity" },
  { key: "max_exit_velocity", label: "Max EV", fmt: "mph", higherBetter: true, gl: "exit_velocity" },
  { key: "barrel_pct", label: "Barrel%", fmt: "pct", higherBetter: true, gl: "barrel_pct" },
  { key: "hard_hit_pct", label: "HardHit%", fmt: "pct", higherBetter: true, gl: "hard_hit_pct" },
  { key: "sweet_spot_pct", label: "SwSpot%", fmt: "pct", higherBetter: true },
  { key: "zone_contact_pct", label: "Z-Con%", fmt: "pct", higherBetter: true },
  { key: "o_contact_pct", label: "O-Con%", fmt: "pct", higherBetter: true },
  { key: "chase_pct", label: "Chase%", fmt: "pct", higherBetter: false, gl: "chase_pct" },
  { key: "whiff_pct", label: "Whiff%", fmt: "pct", higherBetter: false, gl: "whiff_pct" },
  { key: "k_pct", label: "K%", fmt: "pct", higherBetter: false, gl: "k_pct" },
  { key: "bb_pct", label: "BB%", fmt: "pct", higherBetter: true, gl: "bb_pct" },
];

function lbFmt(fmt, v) {
  if (v == null) return " - ";
  if (fmt === "plus") return String(Math.round(v));
  if (fmt === "mph") return v.toFixed(1);
  if (fmt === "dec") return v.toFixed(3).replace(/^0(?=\.)/, "");
  return v.toFixed(1) + "%";
}

function renderLeaderboard() {
  const col = LB_COLUMNS.find((c) => c.key === state.sortKey) || LB_COLUMNS[0];
  state.sortKey = col.key;
  const dir = state.sortDir != null ? state.sortDir : (col.higherBetter ? -1 : 1);
  state.sortDir = dir;
  const minPA = state.minPA || 0;
  const teamF = state.teamFilter || "all";
  const q = state.query.toLowerCase();
  const filtered = state.players.filter((p) =>
    p.hitter_name.toLowerCase().includes(q) &&
    (minPA <= 0 || p.pa == null || p.pa >= minPA) &&
    (teamF === "all" || p.team === teamF));
  filtered.sort((a, b) => dir * compareNullable(sortVal(a, state.sortKey), sortVal(b, state.sortKey)));
  const visible = filtered.slice(0, LEADERBOARD_LIMIT);
  const hasPa = state.players.some((p) => p.pa != null);
  const teams = [...new Set(state.players.map((p) => p.team).filter(Boolean))]
    .sort((a, b) => formatTeamName(a).localeCompare(formatTeamName(b)));
  const head = LB_COLUMNS.map((c) => {
    const on = c.key === state.sortKey;
    const caret = on ? (dir < 0 ? " ▾" : " ▴") : "";
    const lbl = c.gl ? `<span class="g-term" data-gl="${c.gl}">${c.label}</span>` : c.label;
    return `<th class="tt-col lb-th${on ? " is-sorted" : ""}" data-sort="${c.key}" title="Sort by ${c.label}">${lbl}${caret}</th>`;
  }).join("");
  const body = visible.map((p, i) => {
    const cells = LB_COLUMNS.map((c) => {
      const v = c.key === "cs_plus" ? (state.csPlus && state.csPlus.get(p.slug)) : p[c.key];
      const cls = c.key === "cs_plus" && Number.isFinite(v) ? (v >= 110 ? "tt-pos" : v <= 90 ? "tt-neg" : "") : "";
      return `<td class="tt-col ${cls}${c.key === state.sortKey ? " is-sorted" : ""}">${lbFmt(c.fmt, v)}</td>`;
    }).join("");
    const logo = TEAM_LOGOS[p.team] ? `<img class="tt-logo" src="${TEAM_LOGOS[p.team]}" alt="" loading="lazy" onerror="this.remove()">` : "";
    return `<tr><td class="tt-rank">${i + 1}</td>
      <td class="tt-team">${logo}<a class="proj-name" href="#/player/${p.year}/${p.slug}">${escapeHtml(displayName(p.hitter_name))}</a><span class="tt-n">${escapeHtml(formatTeamName(p.team))}</span></td>
      ${cells}</tr>`;
  }).join("");
  app.innerHTML = `
    <section class="toolbar">
      <input class="search-box" type="search" placeholder="Search hitter" value="${escapeHtml(state.query)}" aria-label="Search hitter">
      ${renderYearSelect()}
      <select class="select-box" data-team-filter aria-label="Filter by team">
        <option value="all">All teams</option>
        ${teams.map((t) => `<option value="${escapeHtml(t)}" ${t === teamF ? "selected" : ""}>${escapeHtml(formatTeamName(t))}</option>`).join("")}
      </select>
      ${hasPa ? `<label class="lb-pa">Min PA <input type="number" min="0" step="10" value="${minPA}" data-min-pa></label>` : ""}
      <button class="control-button" type="button" data-reset>Reset</button>
    </section>
    <p class="note-line">${filtered.length.toLocaleString()} hitter${filtered.length === 1 ? "" : "s"}${(hasPa && minPA > 0) ? ` with ${minPA}+ PA` : ""}${teamF !== "all" ? ` on ${escapeHtml(formatTeamName(teamF))}` : ""}, ${state.year}. Click any column header to sort.${filtered.length > visible.length ? ` Showing the top ${visible.length}.` : ""}</p>
    <section class="leaderboard tt-board"><div class="tt-scroll"><table class="tt-table">
      <thead><tr><th class="tt-rank">#</th><th class="tt-team">Player</th>${head}</tr></thead>
      <tbody>${body || `<tr><td colspan="${LB_COLUMNS.length + 2}" class="note-line">No hitters match these filters.</td></tr>`}</tbody>
    </table></div></section>`;
  app.querySelectorAll(".lb-th").forEach((th) => th.addEventListener("click", () => {
    const k = th.getAttribute("data-sort");
    if (k === state.sortKey) { state.sortDir = -dir; }
    else { state.sortKey = k; const c2 = LB_COLUMNS.find((c) => c.key === k); state.sortDir = (c2 && c2.higherBetter) ? -1 : 1; }
    renderLeaderboard();
  }));
  const sb = app.querySelector(".search-box");
  if (sb) sb.addEventListener("input", (e) => {
    state.query = e.target.value;
    const cursor = e.target.selectionStart ?? state.query.length;
    renderLeaderboard();
    const nb = app.querySelector(".search-box");
    if (nb) { nb.focus(); nb.setSelectionRange(cursor, cursor); }
  });
  const tf = app.querySelector("[data-team-filter]");
  if (tf) tf.addEventListener("change", (e) => { state.teamFilter = e.target.value; renderLeaderboard(); });
  const pa = app.querySelector("[data-min-pa]");
  if (pa) pa.addEventListener("change", (e) => { state.minPA = Number(e.target.value) || 0; renderLeaderboard(); });
  const ys = app.querySelector(".year-select");
  if (ys) ys.addEventListener("change", (e) => { setActiveYear(e.target.value); renderLeaderboard(); });
  const rb = app.querySelector("[data-reset]");
  if (rb) rb.addEventListener("click", () => {
    state.query = ""; state.minPA = 0; state.teamFilter = "all"; state.sortKey = "cs_plus"; state.sortDir = null;
    renderLeaderboard();
  });
}

// ---- College Team Tendencies -----------------------------------------------
// Team-level aggregates over the year cohort: which college teams hit the ball
// hardest, chase least, run the best team CS+, etc. Pure aggregation over the
// tracked data we already hold (grouped by the team code on each hitter row).
const TEAM_TENDENCY_METRICS = [
  { key: "cs_plus", label: "Team CS+", fmt: "plus", agg: "mean" },
  { key: "average_exit_velocity", label: "Avg EV", fmt: "mph", agg: "mean" },
  { key: "90th_percentile_exit_velocity", label: "90th EV", fmt: "mph", agg: "mean" },
  { key: "max_exit_velocity", label: "Top EV", fmt: "mph", agg: "max" },
  { key: "barrel_pct", label: "Barrel %", fmt: "pct", agg: "mean" },
  { key: "hard_hit_pct", label: "Hard-Hit %", fmt: "pct", agg: "mean" },
  { key: "chase_pct", label: "Chase %", fmt: "pct", agg: "mean" },
  { key: "whiff_pct", label: "Whiff %", fmt: "pct", agg: "mean" },
  { key: "k_pct", label: "K %", fmt: "pct", agg: "mean" },
  { key: "bb_pct", label: "BB %", fmt: "pct", agg: "mean" },
];
const TEAM_MIN_BATTERS = 3;  // need a few tracked batters before a team is meaningful

function teamMetricValue(players, m) {
  if (m.key === "cs_plus") {
    const vs = players.map((p) => state.csPlus && state.csPlus.get(p.slug)).filter(Number.isFinite);
    return vs.length ? vs.reduce((a, b) => a + b, 0) / vs.length : null;
  }
  const vs = players.map((p) => p[m.key]).filter(Number.isFinite);
  if (!vs.length) return null;
  return m.agg === "max" ? Math.max(...vs) : vs.reduce((a, b) => a + b, 0) / vs.length;
}

function computeTeamTendencies(players) {
  const byTeam = new Map();
  for (const p of players) {
    const t = p.team || "";
    if (!t) continue;
    if (!byTeam.has(t)) byTeam.set(t, []);
    byTeam.get(t).push(p);
  }
  const rows = [];
  for (const [team, ps] of byTeam) {
    if (ps.length < TEAM_MIN_BATTERS) continue;
    const agg = {};
    for (const m of TEAM_TENDENCY_METRICS) agg[m.key] = teamMetricValue(ps, m);
    rows.push({ team, n: ps.length, agg, sample: ps });
  }
  return rows;
}

function renderTeams() {
  const sortKey = TEAM_TENDENCY_METRICS.some((m) => m.key === state.teamSort) ? state.teamSort : "cs_plus";
  const rows = computeTeamTendencies(state.players)
    .sort((a, b) => (b.agg[sortKey] ?? -Infinity) - (a.agg[sortKey] ?? -Infinity));
  const fmtVal = (m, v) => {
    if (v == null) return " - ";
    if (m.fmt === "plus") return String(Math.round(v));
    if (m.fmt === "mph") return v.toFixed(1);
    return v.toFixed(1) + "%";
  };
  const head = TEAM_TENDENCY_METRICS.map((m) =>
    `<th class="tt-col${m.key === sortKey ? " is-sorted" : ""}">${glLabel(m)}</th>`).join("");
  const body = rows.map((r, i) => {
    const cells = TEAM_TENDENCY_METRICS.map((m) => {
      const v = r.agg[m.key];
      const cls = m.fmt === "plus" && Number.isFinite(v) ? (v >= 110 ? "tt-pos" : v <= 90 ? "tt-neg" : "") : "";
      return `<td class="tt-col ${cls}${m.key === sortKey ? " is-sorted" : ""}">${fmtVal(m, v)}</td>`;
    }).join("");
    const logo = TEAM_LOGOS[r.team]
      ? `<img class="tt-logo" src="${TEAM_LOGOS[r.team]}" alt="" loading="lazy" onerror="this.remove()">` : "";
    return `<tr><td class="tt-rank">${i + 1}</td>
      <td class="tt-team">${logo}<span>${escapeHtml(formatTeamName(r.team))}</span><span class="tt-n">${r.n} batters</span></td>
      ${cells}</tr>`;
  }).join("");
  app.innerHTML = `
    <section class="toolbar">
      ${renderYearSelect()}
      <select class="select-box" data-team-sort aria-label="Rank teams by">
        ${TEAM_TENDENCY_METRICS.map((m) => `<option value="${m.key}" ${m.key === sortKey ? "selected" : ""}>Rank by ${m.label}</option>`).join("")}
      </select>
    </section>
    <p class="note-line">College team tendencies for ${state.year}: every team with at least ${TEAM_MIN_BATTERS} tracked batters, aggregated across its hitters. Team CS+ is the mean of its hitters' CS+ (100 = the college average). Top EV is the team's single hardest-hit ball; the rest are team averages.</p>
    <section class="leaderboard tt-board">
      <div class="tt-scroll"><table class="tt-table">
        <thead><tr><th class="tt-rank">#</th><th class="tt-team">Team</th>${head}</tr></thead>
        <tbody>${body || `<tr><td colspan="${TEAM_TENDENCY_METRICS.length + 2}" class="note-line">No teams with enough tracked batters this year.</td></tr>`}</tbody>
      </table></div>
    </section>`;
  const sel = app.querySelector("[data-team-sort]");
  if (sel) sel.addEventListener("change", (e) => { state.teamSort = e.target.value; renderTeams(); });
  const ys = app.querySelector(".year-select");
  if (ys) ys.addEventListener("change", (e) => { setActiveYear(e.target.value); renderTeams(); });
}

// ---- Draft Prospects section (the reverse direction) -----------------------
// Draft-eligible hitters carried INTO CollegeSavant by the conventional college
// box scores we already hold, including prospects with no TrackMan tracking.
// Box-score based and FV-ranked, filterable by draft year. Reads the server-built
// window.CS_DRAFT_PROSPECTS sidecar (college_translation.build).
const PROSPECT_COLS_HIT = [
  { key: "fv", label: "FV", get: (x) => x.fv, t: "ceil", hb: true },
  { key: "year", label: "Yr", get: (x) => x.year, t: "raw", hb: true },
  { key: "avg", label: "AVG", get: (x) => x.box && x.box.avg, t: "dec3", hb: true },
  { key: "obp", label: "OBP", get: (x) => x.box && x.box.obp, t: "dec3", hb: true },
  { key: "slg", label: "SLG", get: (x) => x.box && x.box.slg, t: "dec3", hb: true },
  { key: "iso", label: "ISO", get: (x) => x.box && x.box.iso, t: "dec3", hb: true },
  { key: "woba", label: "wOBA", get: (x) => x.box && x.box.woba, t: "dec3", hb: true },
  { key: "wrc_plus", label: "wRC+", get: (x) => x.box && x.box.wrc_plus, t: "int", hb: true },
  { key: "bb_pct", label: "BB%", get: (x) => x.box && x.box.bb_pct, t: "pct", hb: true },
  { key: "k_pct", label: "K%", get: (x) => x.box && x.box.k_pct, t: "pct", hb: false },
  { key: "pa", label: "PA", get: (x) => x.box && x.box.pa, t: "raw", hb: true },
  { key: "proj_k", label: "Proj A K%", get: (x) => (x.proj && x.proj.k_pct ? x.proj.k_pct.exp : null), t: "pctval", hb: false },
  { key: "proj_bb", label: "Proj A BB%", get: (x) => (x.proj && x.proj.bb_pct ? x.proj.bb_pct.exp : null), t: "pctval", hb: true },
];

function renderProspects() {
  const P = (window.CS_DRAFT_PROSPECTS && window.CS_DRAFT_PROSPECTS.hitters) || [];
  const years = [...new Set(P.map((x) => x.year).filter(Boolean))].sort((a, b) => b - a);
  const yf = state.prospectYear != null ? state.prospectYear : (years[0] || "all");
  const cols = PROSPECT_COLS_HIT;
  const sortKey = state.prospectSort || "fv";
  const col = cols.find((c) => c.key === sortKey) || cols[0];
  const dir = state.prospectDir != null ? state.prospectDir : (col.hb ? -1 : 1);
  const d3 = (v) => v.toFixed(3).replace(/^0(?=\.)/, "");
  const fmt = (t, v) => {
    if (v == null || v === "" || Number.isNaN(v)) return " - ";
    if (t === "ceil") return Math.ceil(v);
    if (t === "dec3") return d3(v);
    if (t === "pct") return (v * 100).toFixed(1) + "%";
    if (t === "pctval") return v.toFixed(1) + "%";
    if (t === "int") return Math.round(v);
    return v;
  };
  const list = P.filter((x) => yf === "all" || x.year === yf).slice();
  list.sort((a, b) => {
    const av = col.get(a), bv = col.get(b);
    const an = av == null || Number.isNaN(av), bn = bv == null || Number.isNaN(bv);
    if (an && bn) return 0;
    if (an) return 1;
    if (bn) return -1;
    return dir * (av - bv);
  });
  const head = cols.map((c) => {
    const on = c.key === sortKey;
    const caret = on ? (dir < 0 ? " ▾" : " ▴") : "";
    return `<th class="tt-col lb-th${on ? " is-sorted" : ""}" data-psort="${c.key}" title="Sort by ${c.label}">${c.label}${caret}</th>`;
  }).join("");
  const body = list.map((x, i) => {
    const nameCell = x.cs
      ? `<a class="proj-name" href="#/player/${x.cs.year}/${x.cs.slug}" title="Open CollegeSavant page">${escapeHtml(x.name || "")}</a>`
      : `<strong>${escapeHtml(x.name || "")}</strong>`;
    // School links to its PROSPX college page (the entity router canonicalizes
    // the raw school string on its end, so no name mapping is needed here).
    const schoolHtml = x.school
      ? `<a class="cs-college-link" href="/prospx/#college=${encodeURIComponent(x.school)}" title="${escapeHtml(x.school)} on PROSPX">${escapeHtml(x.school)}</a>`
      : "";
    const cells = cols.map((c) => `<td class="tt-col${c.key === sortKey ? " is-sorted" : ""}">${fmt(c.t, c.get(x))}</td>`).join("");
    return `<tr><td class="tt-rank">${i + 1}</td>
      <td class="tt-team">${nameCell}<span class="tt-n">${schoolHtml}${x.pos ? " · " + escapeHtml(x.pos) : ""}</span></td>
      ${cells}</tr>`;
  }).join("");
  app.innerHTML = `
    <section class="toolbar">
      <select class="select-box" data-prospect-year aria-label="Draft year">
        <option value="all" ${yf === "all" ? "selected" : ""}>All draft years</option>
        ${years.map((y) => `<option value="${y}" ${y === yf ? "selected" : ""}>${y} draft</option>`).join("")}
      </select>
    </section>
    <div class="panel-title"><span>Draft Prospects in college</span><span>${list.length} hitter prospect${list.length === 1 ? "" : "s"} · conventional college stats, click a column to sort</span></div>
    <p class="trans-note">Draft-eligible hitters carried into CollegeSavant by the college box scores we hold (FanGraphs / NCAA), including prospects with no TrackMan tracking. FV is the consensus board grade, rounded up. Proj A K% / BB% project a Single-A line straight from the college box via a matched-pair model (K% carries signal, r-squared about 0.47; BB% is softer). Names link to a player's CollegeSavant page when they have tracking data.</p>
    <section class="leaderboard tt-board"><div class="tt-scroll"><table class="tt-table">
      <thead><tr><th class="tt-rank">#</th><th class="tt-team">Prospect</th>${head}</tr></thead>
      <tbody>${body || `<tr><td colspan="${cols.length + 2}" class="note-line">No draft prospects with college stats for this year.</td></tr>`}</tbody>
    </table></div></section>`;
  app.querySelectorAll(".lb-th").forEach((th) => th.addEventListener("click", () => {
    const k = th.getAttribute("data-psort");
    if (k === sortKey) { state.prospectDir = -dir; }
    else { state.prospectSort = k; const c2 = cols.find((c) => c.key === k); state.prospectDir = (c2 && c2.hb) ? -1 : 1; }
    renderProspects();
  }));
  const ys = app.querySelector("[data-prospect-year]");
  if (ys) ys.addEventListener("change", (e) => {
    state.prospectYear = e.target.value === "all" ? "all" : Number(e.target.value);
    renderProspects();
  });
}

// ---- College -> Single-A Projections section -------------------------------
// A dedicated home for the translation: an honest "how accurate is this" panel
// from the leave-one-out backtest, then a board of every hitter's projected
// Single-A line (expected + P10-P90 band), ranked by CS+ (the pro profile).
function renderProjections() {
  const E = (window.CS_TRANSLATION && window.CS_TRANSLATION.eval) || {};
  const T = (window.CS_TRANSLATION && window.CS_TRANSLATION.translations) || {};
  const accRows = [["Proj Single-A K%", "hit_k"], ["Proj Single-A BB%", "hit_bb"], ["Proj Single-A OPS", "hit_ops"]]
    .map(([label, k]) => {
      const f = E[k];
      if (!f) return "";
      const cov = f.coverage != null ? Math.round(f.coverage * 100) + "%" : " - ";
      const flag = k === "hit_ops" ? ` <span class="trans-flag">experimental</span>`
                 : (f.r2 != null && f.r2 < 0.10) ? ` <span class="trans-flag">low signal</span>` : "";
      return `<tr><td class="tt-team">${label}${flag}</td>
        <td class="tt-col">${f.r2 != null ? f.r2.toFixed(2) : " - "}</td>
        <td class="tt-col">${f.band_sd != null ? "±" + f.band_sd : " - "}</td>
        <td class="tt-col">${f.mae ?? " - "}</td>
        <td class="tt-col">${cov}</td><td class="tt-col">${f.n ?? " - "}</td></tr>`;
    }).join("");
  const pband = (b, dec) => b == null ? " - " : (dec ? b.exp.toFixed(3).replace(/^0(?=\.)/, "") : b.exp.toFixed(1) + "%");
  const list = state.players
    .map((p) => ({ p, t: T[p.slug], cs: state.csPlus && state.csPlus.get(p.slug) }))
    .filter((x) => x.t && x.t.single_a)
    .sort((a, b) => (b.cs ?? -Infinity) - (a.cs ?? -Infinity))
    .slice(0, LEADERBOARD_LIMIT);
  const body = list.map((x, i) => {
    const sa = x.t.single_a;
    const logo = TEAM_LOGOS[x.p.team] ? `<img class="tt-logo" src="${TEAM_LOGOS[x.p.team]}" alt="" loading="lazy" onerror="this.remove()">` : "";
    return `<tr><td class="tt-rank">${i + 1}</td>
      <td class="tt-team">${logo}<a class="proj-name" href="#/player/${x.p.year}/${x.p.slug}">${escapeHtml(displayName(x.p.hitter_name))}</a></td>
      <td class="tt-col">${plusPill(x.cs, "CS+")}</td>
      <td class="tt-col">${pband(sa.k_pct)}</td>
      <td class="tt-col">${pband(sa.bb_pct)}</td>
      <td class="tt-col">${pband(sa.ops, true)}</td></tr>`;
  }).join("");
  app.innerHTML = `
    <section class="toolbar">${renderYearSelect()}</section>
    <div class="panel-title"><span>How the projection works</span><span>college-to-Single-A statistical translation</span></div>
    <ol class="proj-method">
      <li><strong>Matched pairs.</strong> We take college hitters who later reached Single-A, pair each one's college tracked rate with the Single-A rate they actually posted, and fit how the two relate.</li>
      <li><strong>Regression to the mean.</strong> A college rate is pulled toward the Single-A average by an amount set from how strongly the two levels track in the data, a fitted slope that is shrunk for sample size. An extreme college number is moderated, not copied straight across.</li>
      <li><strong>Bands.</strong> The P10-P90 band is the spread of the model's misses on players it was not fit on (leave-one-out). When coverage sits near 80% in the table below, the band is sized to the data.</li>
      <li><strong>What to trust.</strong> Strikeout rate carries the signal. Walk rate and OPS mostly wash out to the Single-A mean and are flagged; read them as context, not forecasts.</li>
      <li><strong>What it does not do.</strong> No schedule-strength or park adjustment, since no college conference or park table is held. CS+ and the tracked skills describe college performance; they are not a scouting Future Value, which the tracked data does not predict.</li>
    </ol>
    <div class="panel-title" style="margin-top:18px;"><span class="g-term" data-gl="single_a_equivalent">How accurate is this</span><span>leave-one-out backtest on the matched college-to-Single-A pairs</span></div>
    <section class="leaderboard tt-board"><div class="tt-scroll"><table class="tt-table">
      <thead><tr><th class="tt-team">Projection</th><th class="tt-col">r²</th><th class="tt-col">±band</th><th class="tt-col">MAE</th><th class="tt-col">P10-P90 cover</th><th class="tt-col">n pairs</th></tr></thead>
      <tbody>${accRows || `<tr><td colspan="6" class="note-line">No backtest on file.</td></tr>`}</tbody>
    </table></div></section>
    <p class="trans-note">Coverage near 80% means the P10-P90 bands are sized to the data. K% carries the signal (r² ${E.hit_k && E.hit_k.r2 != null ? "~" + E.hit_k.r2.toFixed(2) : "modest"}); BB% and OPS mostly regress to the Single-A mean (low r²) and are shown for context, flagged. Not adjusted for schedule strength or park (no conference / park table held). Stuff and tracked skills are descriptive (the CS+ index), not pro outcome forecasts.</p>
    <div class="panel-title" style="margin-top:18px;"><span>Projected Single-A board</span><span>${list.length} hitters with a projection · ranked by CS+ (pro profile)</span></div>
    <section class="leaderboard tt-board"><div class="tt-scroll"><table class="tt-table">
      <thead><tr><th class="tt-rank">#</th><th class="tt-team">Player</th><th class="tt-col">CS+</th><th class="tt-col">Proj A K%</th><th class="tt-col">Proj A BB%</th><th class="tt-col">Proj A OPS</th></tr></thead>
      <tbody>${body || `<tr><td colspan="6" class="note-line">No projections for this year.</td></tr>`}</tbody>
    </table></div></section>`;
  const ys = app.querySelector(".year-select");
  if (ys) ys.addEventListener("change", (e) => { setActiveYear(e.target.value); renderProjections(); });
}

// The college -> Single-A projection block (the module's through-line). Reads the
// server-built window.CS_TRANSLATION sidecar (college_translation.py) by the
// player's slug. Shows each projected Single-A rate as an expected value + a
// P10-P90 band, with honest flags: K% is the reliable one, BB% carries little
// signal, OPS is experimental. Renders nothing when no translation is on file.
function renderTranslation(player, kind) {
  const T = window.CS_TRANSLATION && window.CS_TRANSLATION.translations;
  const t = T && T[player.slug];
  if (!t || !t.single_a) return "";
  const sa = t.single_a;
  const pct = (x) => (x == null ? "--" : x.toFixed(1) + "%");
  const dec = (x) => (x == null ? "--" : x.toFixed(3).replace(/^0(?=\.)/, ""));
  const row = (label, b, fmt, flag) => {
    if (!b) return "";
    const tag = flag ? ` <span class="trans-flag">${escapeHtml(flag)}</span>` : "";
    return `<div class="trans-row">
      <span class="trans-label">${label}${tag}</span>
      <span class="trans-val">${fmt(b.exp)}</span>
      <span class="trans-band">${fmt(b.lo)} - ${fmt(b.hi)}</span>
    </div>`;
  };
  const rows = [
    row("Proj. Single-A K%", sa.k_pct, pct, null),
    row("Proj. Single-A BB%", sa.bb_pct, pct, sa.bb_pct && sa.bb_pct.low_confidence ? "low confidence" : null),
    row("Proj. Single-A OPS", sa.ops, dec, sa.ops && sa.ops.experimental ? "experimental" : null),
  ].join("");
  if (!rows.trim()) return "";
  return `
    <section class="panel trans-panel">
      <div class="panel-title">
        <span class="g-term" data-gl="single_a_equivalent">Projected Single-A</span>
        <span>expected · P10-P90 band</span>
      </div>
      <div class="trans-grid">
        <div class="trans-head"><span></span><span>Expected</span><span>P10 - P90</span></div>
        ${rows}
      </div>
      <p class="trans-note">Matched-pair projection from this college line to a Single-A
      expectation, fit on our own college-to-Single-A pairs. Not adjusted for schedule
      strength or park. The band is the P10-P90 range, so a wider band means less certain.
      K% is the most reliable; BB% and OPS carry little signal yet and are shown for context.</p>
    </section>`;
}

// Conventional college box score (real outcomes: AVG/OBP/SLG/ISO/wOBA/wRC+) for
// the players we already hold FanGraphs / NCAA stats for, joined by name. The
// tracked data CollegeSavant ships has no in-game outcomes, so this fills the
// gap for draft-relevant players. Renders nothing when no box score is on file.
function renderCollegeBox(player) {
  const T = window.CS_TRANSLATION && window.CS_TRANSLATION.translations;
  const b = T && T[player.slug] && T[player.slug].box;
  if (!b) return "";
  const d3 = (x) => (x == null ? " - " : x.toFixed(3).replace(/^0(?=\.)/, ""));
  const pc = (x) => (x == null ? " - " : (x * 100).toFixed(1) + "%");  // box bb%/k% are decimals
  const cells = [
    ["AVG", d3(b.avg)], ["OBP", d3(b.obp)], ["SLG", d3(b.slg)], ["ISO", d3(b.iso)],
    ["wOBA", d3(b.woba)], ["wRC+", b.wrc_plus != null ? Math.round(b.wrc_plus) : " - "],
    ["BB%", pc(b.bb_pct)], ["K%", pc(b.k_pct)], ["HR", b.hr != null ? b.hr : " - "],
    ["PA", b.pa != null ? b.pa : " - "],
  ].map(([l, v]) => `<div class="box-stat"><span>${l}</span><strong>${v}</strong></div>`).join("");
  return `<section class="panel box-panel">
    <div class="panel-title"><span>College box score</span><span>${b.season || ""} ${escapeHtml(b.level || "NCAA")} · FanGraphs / NCAA</span></div>
    <div class="box-grid">${cells}</div>
  </section>`;
}

function renderPlayer(player) {
  if (!player) {
    app.innerHTML = `<section class="empty"><strong>Player not found.</strong><br><a class="pill" href="#/">Back to leaderboard</a></section>`;
    return;
  }

  const pct = state.percentiles.get(player.slug);
  app.innerHTML = `
    <section class="profile">
      <div class="profile-hero">
        ${teamLogo(player, "large")}
        <div class="profile-title">
          <a class="pill" href="#/">Back to leaderboard</a>
          <button class="pill" id="cs-share" type="button" title="Download this profile as a PNG share card">&#8681; share card</button>
          <h1>${escapeHtml(displayName(player.hitter_name))}</h1>
          <div class="profile-meta">
            <span class="profile-school">${escapeHtml(formatTeamName(player.team))}</span>
            <span class="profile-dot">·</span><span>${player.year} college hitter</span>
            ${plusPill(state.csPlus && state.csPlus.get(player.slug), "CS+")}
          </div>
          <div class="profile-team">${renderYearSelect(availablePlayerYears(player))}</div>
        </div>
      </div>

      ${renderTranslation(player, "hitter")}
      ${renderCollegeBox(player)}

      <div class="profile-grid">
        <section class="panel">
          <div class="panel-title"><span>Percentile Sliders</span><span>${state.players.length} hitters</span></div>
          <div class="slider-list">
            ${METRICS.map((metric) => renderSlider(player, metric, pct[metric.key])).join("")}
          </div>
        </section>

        <section class="panel">
          <div class="panel-title"><span>Batted Balls</span><span>EV x Launch Angle</span></div>
          <div data-export-chart data-export-title="Batted balls - EV x Launch Angle">${renderBattedBallChart(player)}</div>
        </section>
      </div>
    </section>
  `;

  const yearSelect = app.querySelector(".year-select");
  if (yearSelect) {
    yearSelect.addEventListener("change", (event) => {
      setActiveYear(event.target.value);
      const nextPlayer = state.players.find((p) => p.slug === player.slug);
      window.location.hash = nextPlayer ? `#/player/${state.year}/${nextPlayer.slug}` : "#/";
    });
  }
  const shareBtn = app.querySelector("#cs-share");
  if (shareBtn) {
    shareBtn.addEventListener("click", () => {
      if (!window.EEPHUS_HUB) return;
      const rows = METRICS
        .filter((m) => player[m.key] != null)
        .slice(0, 8)
        .map((m) => [m.label, `${formatMetric(player[m.key], m.fmt)}  (${pct && pct[m.key] != null ? pct[m.key] : "-"})`]);
      window.EEPHUS_HUB.shareCard({
        module: "CollegeSavant",
        accentToken: "--accent-red",
        name: displayName(player.hitter_name),
        meta: `${formatTeamName(player.team) || player.teamLabel || ""} · ${player.year} · college hitter`,
        headshotURL: TEAM_LOGOS[player.team] || null,
        tiles: [
          player.xwoba != null ? { label: "xwOBA", value: formatMetric(player.xwoba, "decimal") } : null,
          player.average_exit_velocity != null ? { label: "Avg EV", value: formatMetric(player.average_exit_velocity, "mph") } : null,
          player.barrel_pct != null ? { label: "Barrel%", value: formatMetric(player.barrel_pct, "pct") } : null,
        ].filter(Boolean),
        sections: [{ title: `Percentiles · vs ${state.players.length} qualified hitters`, rows }],
        url: `eephus.io/collegesavant/#/player/${player.year}/${player.slug}`,
        filename: `eephus-collegesavant-${player.slug}.png`,
        caption: "college percentiles vs the qualified pool · CollegeSavant by Joseph Gillis",
      });
    });
  }
}

function renderBattedBallChart(player) {
  const points = state.battedBalls.get(`${player.year}:${player.slug}`) || state.battedBalls.get(player.slug) || [];
  if (!points.length) {
    return `<div class="chart-empty">No batted-ball EV/launch-angle points available.</div>`;
  }

  const width = 640;
  const height = 430;
  const pad = { top: 34, right: 34, bottom: 54, left: 62 };
  const innerW = width - pad.left - pad.right;
  const innerH = height - pad.top - pad.bottom;
  const minEv = 40;
  const maxEv = 125;
  const minLa = -90;
  const maxLa = 90;
  const x = (ev) => pad.left + ((ev - minEv) / (maxEv - minEv)) * innerW;
  const y = (la) => pad.top + (1 - (la - minLa) / (maxLa - minLa)) * innerH;
  const clamp = (value, low, high) => Math.max(low, Math.min(high, value));

  const plotPoints = points.map((point) => {
    const cx = clamp(x(point.ev), pad.left, pad.left + innerW);
    const cy = clamp(y(point.la), pad.top, pad.top + innerH);
    const cls = point.barrel ? "barrel" : point.hard ? "hard" : "";
    return `<circle class="bip-point ${cls}" cx="${cx.toFixed(1)}" cy="${cy.toFixed(1)}" r="4.3"><title>${point.ev.toFixed(1)} mph, ${point.la.toFixed(1)} deg</title></circle>`;
  }).join("");

  return `
    <div class="bip-chart-wrap">
      <svg class="bip-chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="Batted ball exit velocity by launch angle chart">
        <rect class="soft-zone" x="${x(40)}" y="${y(70)}" width="${x(125) - x(40)}" height="${y(-30) - y(70)}"></rect>
        <path class="hard-zone" d="M ${x(95)} ${y(-5)} Q ${x(118)} ${y(20)} ${x(104)} ${y(50)} L ${x(40)} ${y(50)} L ${x(40)} ${y(-5)} Z"></path>
        <rect class="barrel-zone" x="${x(98)}" y="${y(50)}" width="${x(125) - x(98)}" height="${y(26) - y(50)}"></rect>

        ${[-90, -45, 0, 45, 90].map((la) => `<line class="chart-grid" x1="${pad.left}" x2="${pad.left + innerW}" y1="${y(la)}" y2="${y(la)}"></line><text class="chart-small" x="${pad.left - 10}" y="${y(la) + 4}" text-anchor="end">${la} deg</text>`).join("")}
        ${[60, 80, 100, 120].map((ev) => `<line class="chart-grid" x1="${x(ev)}" x2="${x(ev)}" y1="${pad.top}" y2="${pad.top + innerH}"></line><text class="chart-small" x="${x(ev)}" y="${pad.top + innerH + 22}" text-anchor="middle">${ev}</text>`).join("")}

        <line class="chart-axis" x1="${pad.left}" x2="${pad.left}" y1="${pad.top}" y2="${pad.top + innerH}"></line>
        <line class="chart-axis" x1="${pad.left}" x2="${pad.left + innerW}" y1="${y(0)}" y2="${y(0)}"></line>
        <text class="chart-label" x="${pad.left}" y="20">Launch Angle</text>
        <text class="chart-label" x="${pad.left + innerW}" y="${height - 12}" text-anchor="end">Exit Velocity</text>
        <text class="chart-small" x="${x(111.5)}" y="${y(38)}" text-anchor="middle">MLB Barrel Zone</text>

        ${plotPoints}
      </svg>
    </div>
  `;
}

function renderSlider(player, metric, percentile) {
  const pct = percentile ?? 0;
  return `
    <div class="slider-row">
      <div class="slider-label">${glLabel(metric)}</div>
      <div class="slider-value">${formatMetric(player[metric.key], metric.fmt)}</div>
      <div class="track" aria-label="${metric.label} percentile">
        <span class="thumb" style="left: ${pct}%"></span>
      </div>
      <div class="percentile ${pct >= 80 ? "elite" : pct <= 20 ? "low" : ""}">${percentile ?? "--"}</div>
    </div>
  `;
}

function availablePlayerYears(player) {
  const years = state.allPlayers
    .filter((candidate) => candidate.slug === player.slug)
    .map((candidate) => candidate.year);
  return [...new Set(years)].sort((a, b) => b - a);
}

function renderYearSelect(years = state.availableYears) {
  if (years.length <= 1) {
    return `<span class="badge">${years[0] ?? state.year}</span>`;
  }
  return `
    <select class="select-box year-select" aria-label="Select season">
      ${years.map((year) => `<option value="${year}" ${year === state.year ? "selected" : ""}>${year}</option>`).join("")}
    </select>
  `;
}

function topDriverChips(player, limit = 6) {
  const pct = state.percentiles.get(player.slug);
  return METRICS
    .filter((metric) => pct[metric.key] !== null)
    .sort((a, b) => pct[b.key] - pct[a.key])
    .slice(0, limit)
    .map((metric) => {
      const value = pct[metric.key];
      const tone = value >= 70 ? "good" : value <= 30 ? "bad" : "";
      return `<span class="driver-chip ${tone}">${metric.label} ${value}</span>`;
    })
    .join("");
}

function rankForMetric(player, key) {
  const metric = getMetric(key);
  const values = state.players
    .filter((p) => Number.isFinite(p[key]))
    .sort((a, b) => {
      const direction = metric.higherBetter ? -1 : 1;
      return direction * compareNullable(a[key], b[key]);
    });
  return values.findIndex((p) => p.slug === player.slug) + 1;
}

function rankableCount(key) {
  return state.players.filter((p) => Number.isFinite(p[key])).length;
}

function getMetric(key) {
  if (key === "cs_plus") return { key: "cs_plus", label: "CS+", fmt: "number", higherBetter: true };
  return METRICS.find((metric) => metric.key === key) || METRICS[0];
}

// Sort value for a key, including the computed CS+ (not a column on the row).
function sortVal(player, key) {
  return key === "cs_plus" ? (state.csPlus && state.csPlus.get(player.slug)) : player[key];
}

function compareNullable(a, b) {
  const aOk = Number.isFinite(a);
  const bOk = Number.isFinite(b);
  if (!aOk && !bOk) return 0;
  if (!aOk) return 1;
  if (!bOk) return -1;
  return a - b;
}

function formatMetric(value, fmt) {
  if (!Number.isFinite(value)) return "--";
  if (fmt === "decimal") return value.toFixed(3);
  if (fmt === "mph") return value.toFixed(1);
  if (fmt === "pct") return `${value.toFixed(1)}%`;
  return String(value);
}

function displayName(name) {
  const [last, first] = name.split(",").map((part) => part.trim());
  return first ? `${first} ${last}` : name;
}

function slugify(name) {
  return name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
}

function teamLogo(player, size = "") {
  const label = player.team || player.initials;
  const title = formatTeamName(player.team) || player.teamLabel || label;
  const logo = TEAM_LOGOS[player.team];
  const image = logo
    ? `<img src="${logo}" alt="" loading="lazy" onerror="this.style.display='none'; this.nextElementSibling.style.display='block';">`
    : "";
  return `<div class="team-logo ${player.teamClass} ${size}" title="${escapeHtml(title)}" aria-label="${escapeHtml(title)}">${image}<span class="logo-fallback" ${logo ? "style=\"display:none\"" : ""}>${escapeHtml(shortTeam(label))}</span></div>`;
}

function shortTeam(team) {
  const cleaned = String(team || "").replace(/_/g, " ");
  const parts = cleaned.split(/\s+/).filter(Boolean);
  if (parts.length === 1) return parts[0].slice(0, 3).toUpperCase();
  return parts.map((part) => part[0]).join("").slice(0, 3).toUpperCase();
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}
