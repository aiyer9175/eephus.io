const CSV_PATH = "b1g_2025_hitter_xwoba_min30pa.csv";

// Real school names for team codes (owner ask 2026-06-12: badges read
// "Minnesota", never "MIN_GOL"). Unknown codes fall back to a cleaned slug.
const TEAM_DISPLAY_NAMES = {
  ILL_ILL: "Illinois", IU: "Indiana", IOW_HAW: "Iowa", MAR_TER: "Maryland",
  MIC_SPA: "Michigan State", MIC_WOL: "Michigan", MIN_GOL: "Minnesota",
  NEB: "Nebraska", NOR_CAT: "Northwestern", ORE_DUC: "Oregon",
  OSU_BUC: "Ohio State", PEN_NIT: "Penn State", PUR_BOI: "Purdue",
  RUT_SCA: "Rutgers", SOU_TRO: "USC", UCLA: "UCLA", WAS_HUS: "Washington",
};
function formatTeamName(team) {
  const code = String(team || "").trim().toUpperCase();
  if (!code) return "Team";
  return TEAM_DISPLAY_NAMES[code] || code.replace(/_/g, " ");
}

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
  { key: "average_exit_velocity", label: "EV" },
  { key: "90th_percentile_exit_velocity", label: "90th Percentile EV" },
  { key: "zone_contact_pct", label: "Z Contact" },
  { key: "hard_hit_pct", label: "Hard-Hit %" },
  { key: "whiff_pct", label: "Whiff %" },
  { key: "k_minus_bb_pct", label: "K-BB %" },
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
    if (METRICS.some((metric) => metric.key === key)) state.sortKey = key;
    renderLeaderboard();
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
    link.classList.toggle("is-active", route === hash || (hash === "#/" && route === "#/"));
  });
}

function renderHome() {
  app.innerHTML = `
    <section class="toolbar home-toolbar">
      ${renderYearSelect()}
      <a class="control-button" href="#/leaders/xwoba/${state.year}">Full Hitter Leaderboard</a>
    </section>

    <section class="home-intro">
      <h1>Hitter Dashboard</h1>
      <p>Top 10 hitter snapshots for the ${state.year} college dataset.</p>
    </section>

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
            <strong>${formatMetric(player[metric.key], metric.fmt)}</strong>
          </a>
        `).join("")}
      </div>
    </article>
  `;
}

function topRowsForMetric(metric) {
  const direction = metric.higherBetter ? -1 : 1;
  return state.players
    .filter((player) => Number.isFinite(player[metric.key]))
    .sort((a, b) => direction * compareNullable(a[metric.key], b[metric.key]));
}

function renderLeaderboard() {
  const sortMetric = getMetric(state.sortKey);
  const direction = sortMetric.higherBetter ? -1 : 1;
  const filtered = state.players
    .filter((player) => player.hitter_name.toLowerCase().includes(state.query.toLowerCase()))
    .sort((a, b) => direction * compareNullable(a[state.sortKey], b[state.sortKey]));
  const visibleRows = filtered.slice(0, LEADERBOARD_LIMIT);
  const limitNote = filtered.length > visibleRows.length
    ? ` Showing top ${visibleRows.length.toLocaleString()} of ${filtered.length.toLocaleString()} rows; use search to narrow the list.`
    : "";

  app.innerHTML = `
    <section class="toolbar">
      <input class="search-box" type="search" placeholder="Search hitter" value="${escapeHtml(state.query)}" aria-label="Search hitter">
      ${renderYearSelect()}
      <select class="select-box sort-select" aria-label="Sort leaderboard">
        ${METRICS.map((metric) => `<option value="${metric.key}" ${metric.key === state.sortKey ? "selected" : ""}>Sort by ${metric.label}</option>`).join("")}
      </select>
      <button class="control-button" type="button" data-reset>Reset</button>
    </section>

    <p class="note-line">Filtered to hitters above 30 PA. Percentiles compare each hitter against the ${state.players.length}-player ${state.year} dataset; chase, whiff, and K% are inverted so a higher percentile is better.${limitNote}</p>

    <section class="leaderboard">
      <div class="table-head">
        <div>#</div>
        <div>Player</div>
        <div>${glLabel(sortMetric)}</div>
        <div>Avg EV</div>
        <div>90th EV</div>
        <div>Max EV</div>
        <div>Hard Hit</div>
        <div>Drivers</div>
      </div>
      ${visibleRows.map((player, index) => renderPlayerRow(player, index + 1)).join("")}
    </section>
  `;

  app.querySelector(".search-box").addEventListener("input", (event) => {
    state.query = event.target.value;
    const cursor = event.target.selectionStart ?? state.query.length;
    renderLeaderboard();
    const searchBox = app.querySelector(".search-box");
    searchBox.focus();
    searchBox.setSelectionRange(cursor, cursor);
  });

  app.querySelector(".sort-select").addEventListener("change", (event) => {
    state.sortKey = event.target.value;
    window.location.hash = `#/leaders/${state.sortKey}/${state.year}`;
  });

  const yearSelect = app.querySelector(".year-select");
  if (yearSelect) {
    yearSelect.addEventListener("change", (event) => {
      setActiveYear(event.target.value);
      window.location.hash = `#/leaders/${state.sortKey}/${state.year}`;
      renderLeaderboard();
    });
  }

  app.querySelector("[data-reset]").addEventListener("click", () => {
    state.query = "";
    state.sortKey = "xwoba";
    window.location.hash = "#/";
    renderLeaderboard();
  });
}

function renderPlayerRow(player, rank) {
  const chips = topDriverChips(player);
  return `
    <a class="player-row" href="#/player/${player.year}/${player.slug}">
      <div class="rank">${rank}</div>
      <div class="player-cell">
        ${teamLogo(player)}
        <div>
          <span class="player-name">${escapeHtml(displayName(player.hitter_name))}</span>
          <div class="player-sub">
            <span>Hitter</span>
            <span class="badge">${escapeHtml(formatTeamName(player.team))}</span>
            <span class="badge">${player.year}</span>
            <span class="badge">30+ PA</span>
          </div>
        </div>
      </div>
      <div class="metric-main">${formatMetric(player[state.sortKey], getMetric(state.sortKey).fmt)}</div>
      <div>${formatMetric(player.average_exit_velocity, "mph")}</div>
      <div>${formatMetric(player["90th_percentile_exit_velocity"], "mph")}</div>
      <div>${formatMetric(player.max_exit_velocity, "mph")}</div>
      <div>${formatMetric(player.hard_hit_pct, "pct")}</div>
      <div class="driver-chips">${chips}</div>
    </a>
  `;
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

      <div class="profile-grid">
        <section class="panel">
          <div class="panel-title"><span>Percentile Sliders</span><span>${state.players.length} hitters</span></div>
          <div class="slider-list">
            ${METRICS.map((metric) => renderSlider(player, metric, pct[metric.key])).join("")}
          </div>
        </section>

        <section class="panel">
          <div class="panel-title"><span>Batted Balls</span><span>EV x Launch Angle</span></div>
          ${renderBattedBallChart(player)}
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
  return METRICS.find((metric) => metric.key === key) || METRICS[0];
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
