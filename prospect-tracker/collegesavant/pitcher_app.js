const PITCHER_SHAPE_METRICS = [
  { key: "avg_fastball_velo", label: "Avg FB Velo", fmt: "mph", higherBetter: true },
  { key: "avg_ivb", label: "IVB", fmt: "inch", higherBetter: true },
  { key: "avg_extension", label: "Extension", fmt: "feet", higherBetter: true },
  { key: "avg_release_height", label: "Release Ht", fmt: "feet", higherBetter: false },
  { key: "xwoba_against", label: "xwOBA Against", fmt: "decimal", higherBetter: false },
  { key: "average_exit_velocity", label: "Avg EV", fmt: "mph", higherBetter: false },
  { key: "barrel_pct", label: "Barrel %", fmt: "pct", higherBetter: false },
  { key: "hard_hit_pct", label: "Hard-Hit %", fmt: "pct", higherBetter: false },
];

const PITCHER_OUTCOME_METRICS_2024 = [
  { key: "avg_fastball_velo", label: "Avg FB Velo", fmt: "mph", higherBetter: true },
  { key: "avg_ivb", label: "IVB", fmt: "inch", higherBetter: true },
  { key: "avg_extension", label: "Extension", fmt: "feet", higherBetter: true },
  { key: "avg_release_height", label: "Release Ht", fmt: "feet", higherBetter: false },
  { key: "xwoba_against", label: "xwOBA Against", fmt: "decimal", higherBetter: false },
  { key: "average_exit_velocity", label: "Avg EV", fmt: "mph", higherBetter: false },
  { key: "barrel_pct", label: "Barrel %", fmt: "pct", higherBetter: false },
  { key: "hard_hit_pct", label: "Hard-Hit %", fmt: "pct", higherBetter: false },
  { key: "k_pct", label: "K %", fmt: "pct", higherBetter: true },
  { key: "bb_pct", label: "BB %", fmt: "pct", higherBetter: false },
  { key: "chase_pct", label: "Chase %", fmt: "pct", higherBetter: true },
  { key: "z_contact_pct", label: "Z-Contact %", fmt: "pct", higherBetter: false },
  { key: "swinging_strike_pct", label: "SwStr %", fmt: "pct", higherBetter: true },
];

const STUFF_METRIC = { key: "stuff_plus", label: "Stuff+", fmt: "number", higherBetter: true };
const ALL_METRICS = [
  STUFF_METRIC,
  ...dedupeMetrics([...PITCHER_SHAPE_METRICS, ...PITCHER_OUTCOME_METRICS_2024]),
];

const LEADERBOARD_LIMIT = 300;

const PITCHER_HOME_WIDGET_METRICS = [
  { key: "avg_fastball_velo", label: "Fastball Velo" },
  { key: "stuff_plus", label: "Average Stuff+" },
  { key: "swinging_strike_pct", label: "SwStr %" },
  { key: "average_exit_velocity", label: "Average EV" },
  { key: "k_pct", label: "K %" },
  { key: "chase_pct", label: "Chase %" },
];

function dedupeMetrics(metrics) {
  const seen = new Set();
  return metrics.filter((metric) => {
    if (seen.has(metric.key)) return false;
    seen.add(metric.key);
    return true;
  });
}

function activePitcherMetrics() {
  return hasPitchByPitchOutcomes(state.year) ? PITCHER_OUTCOME_METRICS_2024 : PITCHER_SHAPE_METRICS;
}

function activeHeadlineMetrics() {
  return [STUFF_METRIC, ...activePitcherMetrics()];
}

const TEAM_CODE_NAMES = {
  ALV_CCO: "Alvin Community College",
  ANG_STA: "Angelo State University",
  BOC_EAG: "Boston College",
  BUT_COL1: "Butler Community College",
  CAT_IND: "Catawba College",
  CSD_TRI: "UC San Diego",
  CUM_PAT: "Cumberland College",
  CYP_CHR: "Cypress College",
  DIX_STE: "Utah Tech University",
  FAI_STA: "Fairfield University",
  FGCU: "Florida Gulf Coast",
  FRA_MAR1: "Francis Marion University",
  GAR_RUN: "Gardner Webb University",
  Gol_W: "Gold West College",
  HOL_CRU: "Holy Cross",
  ILL_ILL: "Illinois Fighting Illini",
  ILL_WES: "Illinois Wesleyan College",
  IU: "Indiana Hoosiers",
  IOW_CEN: "Iowa Central Community College",
  IOW_HAW: "Iowa Hawkeyes",
  IWC: "Incarnate Word",
  JAC_GAM: "Jacksonville State",
  JOH_LOG: "John A. Logan College",
  JUD: "Jacksonville University",
  KS_GF: "Kent State",
  LIN_CCW: "Linfield University",
  LIN_MEM: "Lincoln Memorial University",
  LIN_TCO: "Lincoln Trail College",
  MAR_TER: "Maryland Terrapins",
  MIC_SPA: "Michigan State Spartans",
  MIC_WOL: "Michigan Wolverines",
  MID_GEO: "Middle Georgia State",
  MIS_COL1: "Mississippi College",
  MOU_OLV: "Mount Olive University",
  MSM_MTN: "Mt. St. Mary's",
  MSU_BDG: "Mississippi State",
  MT: "Memphis University",
  NCB: "Northern Colorado University",
  NEB: "Nebraska Cornhuskers",
  NOK_NOR: "Northern Kentucky University",
  NOR_CAT: "Northwestern Wildcats",
  ORE_DUC: "Oregon Ducks",
  OSU_BUC: "Ohio State Buckeyes",
  PAR_JUN: "Paris Junior College",
  PAT_HEN: "Patrick & Henry Community College",
  PEN_NIT: "Penn State Nittany Lions",
  PEP_WAV: "Pepperdine University",
  PER_STA: "Peru State College",
  PRE_BLH: "Presbyterian College",
  PUR_BOI: "Purdue Boilermakers",
  QUN_RYL: "Queens University Charlotte",
  RAD_HIG: "Radford University",
  RIV_CIT: "Riverside City College",
  RUT_SCA: "Rutgers Scarlet Knights",
  SAC_PIO: "Sacred Heart University",
  SAN_AZT: "San Diego State University",
  SAN_BRO: "Santa Clara College",
  SAN_DON: "University of San Francisco",
  SAN_GAU: "UC Santa Barbara",
  SAN_TOR: "University of San Diego",
  SBU_SEA: "Stony Brook University",
  SIU_SAL: "Southern Illinois University",
  SLC_CCB: "Salt Lake Community College",
  SOU_GAM: "University of South Carolina",
  SOU_GOL: "Southern Mississippi",
  SOU_IND16: "Southern Indiana",
  SOU_TRO: "USC Trojans",
  SOU_WES: "Southwestern University",
  "ST._EDW": "St. Edwards University",
  STB_BON: "St. Bonaventure",
  STE_HAT: "Stetson University",
  STE_LUM: "Stephen F. Austin",
  STM_RAT: "St. Mary's University Texas",
  TCU_HFG: "TCU",
  TEM_LEO: "Temple College",
  THO_M: "St. Thomas University",
  TOL_ROC: "Toledo University",
  TRO_TRJ: "Troy University",
  TUS_PIO: "Tusculum University",
  UCF_KNI: "UCF",
  UCLA: "UCLA",
  UMASS_RIV: "UMass Lowell",
  UMA_AMH: "Umass Amherst",
  UMBC_RET: "UMBC",
  UNC_SEA: "UNC Wilmington",
  UNI_NOR1: "Northwestern Ohio",
  UNI_PIK: "UPike",
  UNI_TEX: "UT Tyler",
  USC_UPS: "USC Upstate",
  UTA_UTE: "Utah",
  UTR_VAQ: "UT Rio Grande Valley",
  UTS_ROA: "UT San Antonio",
  VAL_CRU: "Valparaiso University",
  VIR_CAV: "Virginia",
  VIR_KEY: "Virginia Military Institute",
  VIR_TEC: "Virginia Tech",
  VIR_WIS: "Virginia University at Wise",
  WAK_DEA: "Wake Forest",
  WAS_HUS: "Washington Huskies",
  WCC: "Western Carolina",
  WES_HIL: "Western Kentucky",
  WES_MOU: "West Virginia",
  WES_TEX: "West Texas A&M",
  WHA_JUC: "Wharton County JUCO",
  WIU_LEA: "Western Illinois",
  WMI_BRO: "Western Michigan",
  WM_TRI: "William & Mary",
  WRI_RAI: "Wright State",
  YSU_PEN: "Youngstown State",
};

const SCHOOL_NAMES = {
  ABI: "Abilene Christian",
  AIR: "Air Force",
  ALA: "Alabama",
  ALB: "Albany",
  ARI: "Arizona State",
  ARK: "Arkansas",
  AUB: "Auburn",
  BAY: "Baylor",
  BEL: "Belmont",
  BGS: "Bowling Green",
  BIN: "Binghamton",
  BOS: "Boston College",
  BRA: "Bradley",
  BRO: "Brown",
  BRY: "Bryant",
  BYU: "BYU",
  CAL: "California",
  CAM: "Campbell",
  CAN: "Canisius",
  CAR: "Carson-Newman",
  CEN: "Central Arkansas",
  CHA: "Charlotte",
  CIN: "Cincinnati",
  CIT: "The Citadel",
  CLE: "Clemson",
  COA: "Coastal Carolina",
  COL: "College of Charleston",
  CON: "Connecticut",
  CSU: "Cal State Bakersfield",
  DAL: "Dallas Baptist",
  DAR: "Dartmouth",
  DAY: "Dayton",
  DEL: "Delaware",
  DUK: "Duke",
  ECU: "East Carolina",
  EKU: "Eastern Kentucky",
  ELO: "Elon",
  EMU: "Eastern Michigan",
  EVA: "Evansville",
  FAU: "Florida Atlantic",
  FLA: "Florida",
  FLO: "Florida State",
  FOR: "Fordham",
  FRE: "Fresno State",
  GEO: "Georgia",
  GIT: "Georgia Tech",
  GON: "Gonzaga",
  GRA: "Grand Canyon",
  HAR: "Harvard",
  HBU: "Houston Christian",
  HOF: "Hofstra",
  HOU: "Houston",
  IND: "Indiana State",
  ION: "Iona",
  JMU: "James Madison",
  KAN: "Kansas",
  KEN: "Kennesaw State",
  LAF: "Lafayette",
  LAM: "Lamar",
  LIB: "Liberty",
  LIP: "Lipscomb",
  LOU: "Louisville",
  LOY: "Loyola Marymount",
  LSU: "LSU",
  MAI: "Maine",
  MAR: "Marshall",
  MCN: "McNeese",
  MER: "Mercer",
  MEX: "New Mexico",
  MIA: "Miami",
  MIL: "Milwaukee",
  MIZ: "Missouri",
  MON: "Monmouth",
  MOR: "Morehead State",
  MTSU: "Middle Tennessee",
  MUR: "Murray State",
  NAV: "Navy",
  NEV: "Nevada",
  NEW: "New Orleans",
  NIC: "Nicholls",
  NIU: "Northern Illinois",
  NMS: "New Mexico State",
  NOR: "North Carolina",
  NOT: "Notre Dame",
  OAK: "Oakland",
  OHI: "Ohio",
  OKL: "Oklahoma",
  OLD: "Old Dominion",
  OLE: "Ole Miss",
  ORE: "Oregon",
  PAC: "Pacific",
  PEN: "Penn State",
  RUT: "Rutgers",
  SEA: "Seattle",
  TEX: "Texas",
  TEN: "Tennessee",
  USC: "USC Upstate",
  VIR: "Virginia",
  WOF: "Wofford",
  XAV: "Xavier",
};

const MASCOT_NAMES = {
  ACE: "Purple Aces",
  AGG: "Aggies",
  BEA: "Bears",
  BIS: "Bison",
  BLA: "Black Bears",
  BLU: "Blue Raiders",
  BOB: "Bobcats",
  BOI: "Boilermakers",
  BRA: "Braves",
  BRU: "Bruins",
  BUC: "Buccaneers",
  BUL: "Bulldogs",
  CAM: "Camels",
  CAR: "Cardinals",
  CAT: "Wildcats",
  CHA: "Chanticleers",
  COL: "Colonels",
  COM: "Commodores",
  COU: "Cougars",
  COW: "Cowboys",
  DUC: "Ducks",
  DUK: "Dukes",
  EAG: "Eagles",
  FAL: "Falcons",
  FLA: "Flames",
  FLY: "Flyers",
  GAE: "Gaels",
  GAT: "Gators",
  GRE: "Green Wave",
  GRI: "Golden Griffins",
  GWI: "George Washington",
  HAW: "Hawkeyes",
  HFG: "Horned Frogs",
  HOY: "Hoyas",
  HUS: "Huskies",
  IRI: "Fighting Irish",
  JAY: "Jayhawks",
  LAN: "Lancers",
  LEP: "Leopards",
  LIO: "Lions",
  LON: "Longhorns",
  LOB: "Lobos",
  MAV: "Mavericks",
  MID: "Midshipmen",
  MON: "Monarchs",
  MUS: "Musketeers",
  NIT: "Nittany Lions",
  OWL: "Owls",
  PAN: "Panthers",
  PHO: "Phoenix",
  PIR: "Pirates",
  PRI: "Privateers",
  RAC: "Racers",
  RAM: "Rams",
  RAZ: "Razorbacks",
  REB: "Rebels",
  RED: "Redhawks",
  SCA: "Scarlet Knights",
  SEM: "Seminoles",
  SPA: "Spartans",
  SUN: "Sun Devils",
  TAR: "Tar Heels",
  TER: "Terrapins",
  TIG: "Tigers",
  TRO: "Trojans",
  UNI: "Panthers",
  UNI2: "Panthers",
  VOL: "Volunteers",
  WAR: "Warhawks",
  WIL: "Wildcats",
  WOL: "Wolverines",
  YEL: "Yellow Jackets",
};

const state = {
  allPitchers: [],
  allPitches: [],
  pitchers: [],
  pitches: [],
  availableYears: [],
  year: 2026,
  sortKey: "stuff_plus",
  query: "",
  percentiles: new Map(),
  pitchPercentiles: new Map(),
};

const app = document.querySelector("#app");

init();

function init() {
  try {
    state.allPitchers = (window.PITCHER_DATA || []).map(normalizePitcher);
    state.allPitches = (window.PITCHER_PITCH_DATA || []).map(normalizePitchRow);
    state.availableYears = [...new Set(state.allPitchers.map((pitcher) => pitcher.year))].sort((a, b) => b - a);
    state.year = state.availableYears.includes(2025) ? 2025 : (state.availableYears[0] || 2026);
    setActiveYear(yearFromHash(window.location.hash) || state.year);
    window.addEventListener("hashchange", render);
    render();
  } catch (error) {
    app.innerHTML = `<section class="empty"><strong>Could not load pitcher data.</strong><br>${escapeHtml(error.message)}</section>`;
  }
}

function normalizePitchRow(row) {
  return {
    ...row,
    pitcher_id: String(row.pitcher_id),
    year: Number(row.year || 2026),
    pitch_count: Number(row.pitch_count || 0),
    stuff_plus: row.stuff_plus === null || row.stuff_plus === "" ? null : Number(row.stuff_plus),
    mph: row.mph === null || row.mph === "" ? null : Number(row.mph),
    features: row.features && typeof row.features === "object" ? row.features : {},
    drivers: Array.isArray(row.drivers)
      ? row.drivers.map((driver) => ({
          ...driver,
          value: Number(driver.value),
        })).filter((driver) => Number.isFinite(driver.value))
      : [],
  };
}

function normalizePitcher(row) {
  const pitcher = { ...row };
  for (const metric of ALL_METRICS) {
    pitcher[metric.key] = row[metric.key] === null || row[metric.key] === "" ? null : Number(row[metric.key]);
  }
  pitcher.pitch_count = Number(row.pitch_count || 0);
  pitcher.year = Number(row.year || 2026);
  pitcher.slug = slugify(`${pitcher.pitcher_name}-${pitcher.pitcher_id}`);
  pitcher.initials = pitcher.pitcher_name
    .split(/[,\s]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0])
    .join("")
    .toUpperCase();
  pitcher.teamClass = pitcher.team ? `team-${slugify(pitcher.team)}` : "team-unknown";
  return pitcher;
}

function setActiveYear(year) {
  const numericYear = Number(year);
  state.year = state.availableYears.includes(numericYear) ? numericYear : (state.availableYears[0] || numericYear);
  state.pitchers = state.allPitchers.filter((pitcher) => pitcher.year === state.year);
  state.pitches = state.allPitches.filter((pitch) => pitch.year === state.year);
  state.percentiles = computePercentiles(state.pitchers);
  state.pitchPercentiles = computePitchPercentiles(state.pitches);
  if (!activeHeadlineMetrics().some((metric) => metric.key === state.sortKey)) {
    state.sortKey = "stuff_plus";
  }
}

function yearFromHash(hash) {
  const playerMatch = String(hash || "").match(/^#\/player\/(\d{4})\//);
  if (playerMatch) return Number(playerMatch[1]);
  const leaderMatch = String(hash || "").match(/^#\/leaders\/[^/]+\/(\d{4})$/);
  if (leaderMatch) return Number(leaderMatch[1]);
  return null;
}

function computePitchPercentiles(pitches) {
  const pools = new Map();
  for (const pitch of pitches) {
    if (!Number.isFinite(pitch.stuff_plus)) continue;
    if (!pools.has(pitch.pitch_type)) pools.set(pitch.pitch_type, []);
    pools.get(pitch.pitch_type).push(pitch.stuff_plus);
  }
  for (const values of pools.values()) values.sort((a, b) => a - b);

  const byPitch = new Map();
  for (const pitch of pitches) {
    if (!Number.isFinite(pitch.stuff_plus)) continue;
    const pool = pools.get(pitch.pitch_type) || [];
    if (pool.length < 2) continue;
    const percentile = percentileFromPool(pool, pitch.stuff_plus);
    byPitch.set(pitchKey(pitch), Math.max(1, Math.min(99, percentile)));
  }
  return byPitch;
}

function computePercentiles(pitchers) {
  const byPitcher = new Map();
  const pools = new Map();

  for (const metric of ALL_METRICS) {
    pools.set(metric.key, pitchers
      .map((p) => p[metric.key])
      .filter((value) => Number.isFinite(value))
      .sort((a, b) => a - b));
  }

  for (const pitcher of pitchers) {
    const values = {};
    for (const metric of ALL_METRICS) {
      const pool = pools.get(metric.key) || [];
      const value = pitcher[metric.key];
      if (!Number.isFinite(value) || pool.length < 2) {
        values[metric.key] = null;
        continue;
      }
      if ((metric.key === "barrel_pct" || metric.key === "hard_hit_pct") && value === 0) {
        values[metric.key] = 99;
        continue;
      }
      let percentile = percentileFromPool(pool, value);
      if (!metric.higherBetter) percentile = 100 - percentile;
      values[metric.key] = Math.max(1, Math.min(99, percentile));
    }
    byPitcher.set(pitcher.slug, values);
  }
  return byPitcher;
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
    renderPitcher(state.pitchers.find((p) => p.slug === slug));
    return;
  }
  if (hash.startsWith("#/leaders/")) {
    const key = hash.replace("#/leaders/", "").split("/")[0];
    if (activeHeadlineMetrics().some((metric) => metric.key === key)) state.sortKey = key;
    renderLeaderboard();
    return;
  }
  renderHome();
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
      <a class="control-button" href="#/leaders/stuff_plus/${state.year}">Full Pitcher Leaderboard</a>
    </section>

    <section class="home-intro">
      <h1>Pitcher Dashboard</h1>
      <p>Top 10 pitcher snapshots for the ${state.year} college dataset.</p>
    </section>

    <section class="widget-grid">
      ${PITCHER_HOME_WIDGET_METRICS.map((item) => renderTopWidget({ ...getMetric(item.key), label: item.label })).join("")}
    </section>
  `;

  app.querySelector(".year-select").addEventListener("change", (event) => {
    setActiveYear(event.target.value);
    window.location.hash = "#/";
    renderHome();
  });
}

function renderTopWidget(metric) {
  const rows = topRowsForMetric(metric).slice(0, 10);
  return `
    <article class="top-widget">
      <div class="widget-title">
        <span>${escapeHtml(metric.label)}</span>
        <a href="#/leaders/${metric.key}/${state.year}">View All</a>
      </div>
      <div class="widget-list">
        ${rows.map((pitcher, index) => `
          <a class="widget-row" href="#/player/${pitcher.year}/${pitcher.slug}">
            <span class="widget-rank">${index + 1}</span>
            <span class="widget-name">${escapeHtml(displayName(pitcher.pitcher_name))}</span>
            <span class="widget-team">${pitcher.team ? `<img class="widget-logo" src="logos/${escapeHtml(pitcher.team)}.png" alt="" loading="lazy" onerror="this.remove()">` : ""}${escapeHtml(formatTeamName(pitcher.team))}</span>
            <strong>${formatMetric(pitcher[metric.key], metric.fmt)}</strong>
          </a>
        `).join("")}
      </div>
    </article>
  `;
}

function topRowsForMetric(metric) {
  const direction = metric.higherBetter ? -1 : 1;
  return state.pitchers
    .filter((pitcher) => Number.isFinite(pitcher[metric.key]))
    .sort((a, b) => compareMetric(a[metric.key], b[metric.key], direction));
}

function renderLeaderboard() {
  const metric = getMetric(state.sortKey);
  const direction = metric.higherBetter ? -1 : 1;
  const filtered = state.pitchers
    .filter((pitcher) => pitcher.pitcher_name.toLowerCase().includes(state.query.toLowerCase()))
    .sort((a, b) => compareMetric(a[state.sortKey], b[state.sortKey], direction));
  const visibleRows = filtered.slice(0, LEADERBOARD_LIMIT);
  const limitNote = filtered.length > visibleRows.length
    ? ` Showing top ${visibleRows.length.toLocaleString()} of ${filtered.length.toLocaleString()} rows; use search to narrow the list.`
    : "";

  app.innerHTML = `
    <section class="toolbar">
      <input class="search-box" type="search" placeholder="Search pitcher" value="${escapeHtml(state.query)}" aria-label="Search pitcher">
      ${renderYearSelect()}
      <select class="select-box sort-select" aria-label="Sort leaderboard">
        ${activeHeadlineMetrics().map((m) => `<option value="${m.key}" ${m.key === state.sortKey ? "selected" : ""}>Sort by ${m.label}</option>`).join("")}
      </select>
      <button class="control-button" type="button" data-reset>Reset</button>
    </section>

    <p class="note-line">Filtered to pitchers with 50+ pitches. Percentiles compare each pitcher against the ${state.pitchers.length}-pitcher NCAA ${state.year} dataset. Red is good, blue is bad.${limitNote}</p>

    <section class="leaderboard">
      <div class="table-head pitcher-head">
        <div>#</div>
        <div>Pitcher</div>
        <div>Stuff+</div>
        <div>FB Velo</div>
        <div>xwOBA</div>
        <div>Avg EV</div>
        <div>Hard Hit</div>
        <div>Drivers</div>
      </div>
      ${visibleRows.map((pitcher, index) => renderPitcherRow(pitcher, index + 1)).join("")}
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

  app.querySelector(".year-select").addEventListener("change", (event) => {
    setActiveYear(event.target.value);
    window.location.hash = `#/leaders/${state.sortKey}/${state.year}`;
    renderLeaderboard();
  });

  app.querySelector("[data-reset]").addEventListener("click", () => {
    state.query = "";
    state.sortKey = "stuff_plus";
    window.location.hash = "#/";
    renderLeaderboard();
  });
}

function renderPitcherRow(pitcher, rank) {
  return `
    <a class="player-row" href="#/player/${pitcher.year}/${pitcher.slug}">
      <div class="rank">${rank}</div>
      <div class="player-cell">
        ${teamBadge(pitcher)}
        <div>
          <span class="player-name">${escapeHtml(displayName(pitcher.pitcher_name))}</span>
          <div class="player-sub">
            <span>Pitcher</span>
            <span class="badge">${escapeHtml(formatTeamName(pitcher.team))}</span>
            <span class="badge">${pitcher.year}</span>
            <span class="badge">${pitcher.pitch_count} pitches</span>
          </div>
        </div>
      </div>
      <div class="metric-main">${formatMetric(pitcher.stuff_plus, "number")}</div>
      <div>${formatMetric(pitcher.avg_fastball_velo, "mph")}</div>
      <div>${formatMetric(pitcher.xwoba_against, "decimal")}</div>
      <div>${formatMetric(pitcher.average_exit_velocity, "mph")}</div>
      <div>${formatMetric(pitcher.hard_hit_pct, "pct")}</div>
      <div class="driver-chips">${topDriverChips(pitcher)}</div>
    </a>
  `;
}

function _wireCsShare(pitcher, pct) {
  const btn = app.querySelector("#cs-share");
  if (!btn) return;
  btn.addEventListener("click", () => {
    if (!window.EEPHUS_HUB) return;
    const rows = activePitcherMetrics()
      .filter((m) => pitcher[m.key] != null)
      .slice(0, 8)
      .map((m) => [m.label, `${formatMetric(pitcher[m.key], m.fmt)}  (${pct && pct[m.key] != null ? pct[m.key] : "-"})`]);
    window.EEPHUS_HUB.shareCard({
      module: "CollegeSavant",
      accentToken: "--accent-red",
      name: displayName(pitcher.pitcher_name),
      meta: `${formatTeamName(pitcher.team)} · ${pitcher.year} · college pitcher`,
      headshotURL: pitcher.team ? `logos/${pitcher.team}.png` : null,
      tiles: [
        pitcher.stuff_plus != null ? { label: "Stuff+", value: formatMetric(pitcher.stuff_plus, "number") } : null,
        pitcher.avg_fastball_velo != null ? { label: "FB velo", value: formatMetric(pitcher.avg_fastball_velo, "mph") } : null,
        pitcher.xwoba_against != null ? { label: "xwOBA agn", value: formatMetric(pitcher.xwoba_against, "decimal") } : null,
      ].filter(Boolean),
      sections: [{ title: `Percentiles · vs ${state.pitchers.length} qualified pitchers`, rows }],
      url: `eephus.io/collegesavant/pitcher_index.html#/player/${pitcher.year}/${pitcher.slug}`,
      filename: `eephus-collegesavant-${pitcher.slug}.png`,
      caption: "college percentiles vs the qualified pool · CollegeSavant by Joseph Gillis",
    });
  });
}

function renderPitcher(pitcher) {
  if (!pitcher) {
    app.innerHTML = `<section class="empty"><strong>Pitcher not found.</strong><br><a class="pill" href="#/">Back to leaderboard</a></section>`;
    return;
  }
  const pct = state.percentiles.get(pitcher.slug);
  app.innerHTML = `
    <section class="profile">
      <div class="profile-hero">
        ${teamBadge(pitcher, "large")}
        <div class="profile-title">
          <a class="pill" href="#/">Back to leaderboard</a>
          <button class="pill" id="cs-share" type="button" title="Download this profile as a PNG share card">&#8681; share card</button>
          <h1>${escapeHtml(displayName(pitcher.pitcher_name))}</h1>
          <div class="profile-team">${teamBadge(pitcher, "mini")}<span>${escapeHtml(formatTeamName(pitcher.team))}</span>${renderYearSelect(availablePlayerYears(pitcher))}</div>
          <p>${escapeHtml(profileSummaryText())}</p>
          <div class="driver-chips" style="margin-top: 12px">${topDriverChips(pitcher, 8)}</div>
        </div>
        <div class="hero-stats">
          <div class="hero-stat"><span>Stuff+</span><strong>${formatMetric(pitcher.stuff_plus, "number")}</strong></div>
          <div class="hero-stat"><span>Stuff+ pctile</span><strong>${pct.stuff_plus ?? "--"}</strong></div>
          <div class="hero-stat"><span>FB Velo</span><strong>${formatMetric(pitcher.avg_fastball_velo, "mph")}</strong></div>
          <div class="hero-stat"><span>Pitch Count</span><strong>${pitcher.pitch_count}</strong></div>
          <div class="hero-stat"><span>Year</span><strong>${pitcher.year}</strong></div>
        </div>
      </div>

      <div class="profile-grid">
        <section class="panel">
          <div class="panel-title"><span>Pitcher Sliders</span><span>${state.pitchers.length} pitchers</span></div>
          <div class="slider-list">
            ${activePitcherMetrics().map((metric) => renderSlider(pitcher, metric, pct[metric.key])).join("")}
          </div>
        </section>

        <section class="panel">
          <div class="panel-title"><span>Model Summary</span><span>Stuff+</span></div>
          ${renderPitchShapePlot(pitcher)}
          ${renderPitchMixSummary(pitcher)}
          <div class="slider-list">
            ${renderPitchTypeStuff(pitcher)}
          </div>
        </section>
      </div>
    </section>
  `;

  app.querySelector(".year-select").addEventListener("change", (event) => {
    setActiveYear(event.target.value);
    const nextPitcher = state.pitchers.find((p) => p.slug === pitcher.slug);
    window.location.hash = nextPitcher ? `#/player/${state.year}/${nextPitcher.slug}` : "#/";
  });  _wireCsShare(pitcher, pct);
}

function renderPitchTypeStuff(pitcher) {
  const rows = state.pitches
    .filter((pitch) => String(pitch.pitcher_id) === String(pitcher.pitcher_id) && pitch.year === pitcher.year)
    .sort((a, b) => b.pitch_count - a.pitch_count);

  if (!rows.length) {
    return `<div class="chart-empty">No pitch mix values available for this pitcher.</div>`;
  }

  return rows.map((pitch) => {
    const percentile = state.pitchPercentiles.get(pitchKey(pitch));
    const pct = percentile ?? 0;
    return `
      <div class="slider-row pitch-type-row ${percentile == null ? "is-missing" : ""}">
        <div class="slider-label">${escapeHtml(shortPitchName(pitch.pitch_type))}</div>
        <div class="slider-value">${formatMetric(pitch.stuff_plus, "number")}</div>
        <div class="track" aria-label="${escapeHtml(pitch.pitch_type)} Stuff+ percentile">
          ${percentile == null ? "" : `<span class="thumb" style="left: ${pct}%"></span>`}
        </div>
        <div class="percentile ${percentile == null ? "missing" : pct >= 80 ? "elite" : pct <= 20 ? "low" : ""}">${percentile ?? "--"}</div>
      </div>
      <div class="pitch-context">${pitch.pitch_count} pitches${Number.isFinite(pitch.mph) ? ` · ${formatMetric(pitch.mph, "mph")}` : ""}</div>
      ${renderStuffDriverGraph(pitch)}
    `;
  }).join("");
}

function renderPitchMixSummary(pitcher) {
  const rows = state.pitches
    .filter((pitch) => String(pitch.pitcher_id) === String(pitcher.pitcher_id) && pitch.year === pitcher.year)
    .sort((a, b) => b.pitch_count - a.pitch_count);

  if (!rows.length) {
    return "";
  }

  return `
    <div class="pitch-mix-strip" aria-label="Pitch mix">
      ${rows.map((pitch) => `
        <span class="pitch-mix-chip ${Number.isFinite(pitch.stuff_plus) ? "" : "is-unscored"}">
          <strong>${escapeHtml(shortPitchName(pitch.pitch_type))}</strong>
          <span>${pitch.pitch_count} pitches</span>
          <em>${Number.isFinite(pitch.stuff_plus) ? formatMetric(pitch.stuff_plus, "number") : "--"}</em>
        </span>
      `).join("")}
    </div>
  `;
}

function renderPitchShapePlot(pitcher) {
  if (!hasPitchByPitchOutcomes(pitcher.year)) return "";

  const shapeData = window[`PITCH_SHAPES_${pitcher.year}`] || {};
  const rawRows = shapeData[String(pitcher.pitcher_id)] || [];
  const rows = rawRows
    .map((point) => ({
      pitch_type: point[0],
      hb: Number(point[1]),
      ivb: Number(point[2]),
    }))
    .filter((pitch) => Number.isFinite(pitch.hb) && Number.isFinite(pitch.ivb));

  if (!rows.length) {
    return `<div class="chart-empty">No pitch-shape IVB/HB values available.</div>`;
  }

  const width = 660;
  const height = 330;
  const pad = { top: 26, right: 26, bottom: 52, left: 56 };
  const innerW = width - pad.left - pad.right;
  const innerH = height - pad.top - pad.bottom;
  const minHb = -25;
  const maxHb = 25;
  const minIvb = -15;
  const maxIvb = 25;
  const x = (hb) => pad.left + ((hb - minHb) / (maxHb - minHb)) * innerW;
  const y = (ivb) => pad.top + (1 - (ivb - minIvb) / (maxIvb - minIvb)) * innerH;
  const clamp = (value, low, high) => Math.max(low, Math.min(high, value));
  const pitchCounts = rows.reduce((counts, pitch) => {
    const name = pitch.pitch_type || "Other";
    counts.set(name, (counts.get(name) || 0) + 1);
    return counts;
  }, new Map());
  const legendRows = Array.from(pitchCounts.entries()).sort((a, b) => b[1] - a[1]);
  const points = rows.map((pitch) => {
    const cx = clamp(x(pitch.hb), pad.left, pad.left + innerW);
    const cy = clamp(y(pitch.ivb), pad.top, pad.top + innerH);
    const color = pitchColor(pitch.pitch_type);
    return `
      <circle class="shape-dot" cx="${cx.toFixed(1)}" cy="${cy.toFixed(1)}" r="2.4" fill="${color}">
        <title>${escapeHtml(shortPitchName(pitch.pitch_type))}: HB ${pitch.hb.toFixed(1)} in, IVB ${pitch.ivb.toFixed(1)} in</title>
      </circle>
    `;
  }).join("");

  const legend = legendRows.map(([pitchType, count]) => `
    <span><i style="background:${pitchColor(pitchType)}"></i>${escapeHtml(shortPitchName(pitchType))} <em>${count}</em></span>
  `).join("");

  return `
    <div class="pitch-shape-card">
      <svg class="pitch-shape-plot" viewBox="0 0 ${width} ${height}" role="img" aria-label="Pitch shape plot, horizontal break by induced vertical break">
        ${[-20, -10, 0, 10, 20].map((hb) => `<line class="shape-grid" x1="${x(hb)}" x2="${x(hb)}" y1="${pad.top}" y2="${pad.top + innerH}"></line><text class="shape-tick" x="${x(hb)}" y="${pad.top + innerH + 22}" text-anchor="middle">${hb}</text>`).join("")}
        ${[-10, 0, 10, 20].map((ivb) => `<line class="shape-grid" x1="${pad.left}" x2="${pad.left + innerW}" y1="${y(ivb)}" y2="${y(ivb)}"></line><text class="shape-tick" x="${pad.left - 10}" y="${y(ivb) + 4}" text-anchor="end">${ivb}</text>`).join("")}
        <line class="shape-axis" x1="${pad.left}" x2="${pad.left + innerW}" y1="${y(0)}" y2="${y(0)}"></line>
        <line class="shape-axis" x1="${x(0)}" x2="${x(0)}" y1="${pad.top}" y2="${pad.top + innerH}"></line>
        <text class="shape-label" x="${pad.left + innerW}" y="${height - 12}" text-anchor="end">Horizontal Break</text>
        <text class="shape-label" x="${pad.left}" y="18">IVB</text>
        <g class="shape-dots">${points}</g>
      </svg>
      <div class="shape-legend">${legend}</div>
    </div>
  `;
}

function renderStuffDriverGraph(pitch) {
  const featureDrivers = pitch.drivers || [];
  if (!featureDrivers.length || !Number.isFinite(pitch.stuff_plus)) {
    return `<div class="driver-graph-empty">No Stuff+ driver values available for this pitch.</div>`;
  }

  const overallDelta = pitch.stuff_plus - 100;
  const featureTotal = featureDrivers.reduce((sum, driver) => sum + (Number(driver.value) || 0), 0);
  const modelBase = overallDelta - featureTotal;
  const drivers = [...featureDrivers];
  if (Math.abs(modelBase) >= 0.05) {
    drivers.push({
      key: "ModelBase",
      label: "Model Base",
      value: Number(modelBase.toFixed(2)),
    });
  }

  const visibleDrivers = drivers.filter((driver) => Math.abs(driver.value) >= 0.05);
  const positiveDrivers = visibleDrivers.filter((driver) => driver.value > 0);
  const negativeDrivers = visibleDrivers.filter((driver) => driver.value < 0);
  const positiveTotal = positiveDrivers.reduce((sum, driver) => sum + driver.value, 0);
  const negativeTotal = negativeDrivers.reduce((sum, driver) => sum + Math.abs(driver.value), 0);
  const scale = Math.max(18, positiveTotal, negativeTotal, Math.abs(overallDelta));
  let positiveOffset = 0;
  let negativeOffset = 0;

  const positiveSegments = positiveDrivers.map((driver, index) => {
    const height = Math.max(1.5, (driver.value / scale) * 44);
    const style = `height:${height}%;bottom:calc(50% + ${positiveOffset}%);--segment:${index};--feature-color:${featureColor(driver.key)};`;
    positiveOffset += height;
    return `<span class="driver-segment boost" style="${style}" title="${escapeHtml(driver.label)} ${formatSigned(driver.value)}"></span>`;
  }).join("");

  const negativeSegments = negativeDrivers.map((driver, index) => {
    const height = Math.max(1.5, (Math.abs(driver.value) / scale) * 44);
    const style = `height:${height}%;top:calc(50% + ${negativeOffset}%);--segment:${index};--feature-color:${featureColor(driver.key)};`;
    negativeOffset += height;
    return `<span class="driver-segment drag" style="${style}" title="${escapeHtml(driver.label)} ${formatSigned(driver.value)}"></span>`;
  }).join("");

  const markerTop = Math.max(4, Math.min(96, 50 - (overallDelta / scale) * 44));
  const sortedDrivers = [...drivers].sort((a, b) => Math.abs(b.value) - Math.abs(a.value));
  const legendDrivers = [...drivers].sort((a, b) => a.label.localeCompare(b.label));
  return `
    <div class="stuff-driver-card">
      <div class="driver-graph">
        <div class="driver-axis"></div>
        <div class="driver-stack" aria-label="${escapeHtml(pitch.pitch_type)} Stuff+ drivers">
          ${positiveSegments}
          ${negativeSegments}
          <span class="overall-marker" style="top:${markerTop}%"></span>
        </div>
        <div class="driver-scale top">+</div>
        <div class="driver-scale mid">100</div>
        <div class="driver-scale bottom">-</div>
        <div class="driver-legend">
          ${legendDrivers.map((driver) => `<span><i style="background:${featureColor(driver.key)}"></i>${escapeHtml(driver.label)}</span>`).join("")}
        </div>
      </div>
      <div class="driver-breakdown">
        ${sortedDrivers.map((driver) => `
          <span class="driver-item ${driver.value >= 0 ? "boost" : "drag"}">
            <span>${escapeHtml(driver.label)} <em>${escapeHtml(formatDriverFeatureValue(pitch, driver.key))}</em></span>
            <strong>${formatSigned(driver.value)}</strong>
          </span>
        `).join("")}
        <span class="driver-item overall"><span>Overall</span><strong>${formatMetric(pitch.stuff_plus, "number")}</strong></span>
      </div>
    </div>
  `;
}

function featureColor(key) {
  const colors = {
    RelSpeed: "#d64a45",
    InducedVertBreak: "#2f78bd",
    HorzBreak: "#f0a23a",
    RelHeight: "#6b55b8",
    Extension: "#27966f",
    SpinRate: "#bf4f90",
    HorzRelAngle: "#6f8798",
    VAA: "#111827",
    ModelBase: "#10243e",
  };
  return colors[key] || "#10243e";
}

function pitchColor(pitchType) {
  const colors = {
    Fastball: "#d64a45",
    FourSeamFastBall: "#d64a45",
    TwoSeamFastBall: "#e46b44",
    Sinker: "#f0a23a",
    Slider: "#2f78bd",
    Sweeper: "#6b55b8",
    Curveball: "#27966f",
    ChangeUp: "#bf4f90",
    Cutter: "#6f8798",
    Splitter: "#10243e",
  };
  return colors[pitchType] || "#8a96a3";
}

function renderSlider(pitcher, metric, percentile) {
  if (percentile === null || percentile === undefined) {
    return `
      <div class="slider-row is-missing">
        <div class="slider-label">${metric.label}</div>
        <div class="slider-value">${formatMetric(pitcher[metric.key], metric.fmt)}</div>
        <div class="track" aria-label="${metric.label} unavailable"></div>
        <div class="percentile missing">--</div>
      </div>
    `;
  }
  const pct = percentile;
  return `
    <div class="slider-row">
      <div class="slider-label">${metric.label}</div>
      <div class="slider-value">${formatMetric(pitcher[metric.key], metric.fmt)}</div>
      <div class="track" aria-label="${metric.label} percentile">
        <span class="thumb" style="left: ${pct}%"></span>
      </div>
      <div class="percentile ${pct >= 80 ? "elite" : pct <= 20 ? "low" : ""}">${percentile ?? "--"}</div>
    </div>
  `;
}

function profileSummaryText() {
  if (hasPitchByPitchOutcomes(state.year)) {
    return `Stuff+ is scored from the saved pitch models. Pitcher sliders use ${state.year} pitch-by-pitch outcomes for xwOBA against, contact quality, plate discipline, and swing-and-miss rates.`;
  }
  return "Stuff+ is scored from the saved pitch models. xwOBA/contact metrics are estimated from aggregated EV/LA rows, while pitch-shape sliders use weighted averages from the source pitch groups.";
}

function hasPitchByPitchOutcomes(year) {
  return year === 2024 || year === 2025;
}

function pitchKey(pitch) {
  return `${pitch.year}::${pitch.pitcher_id}::${pitch.pitch_type}`;
}

function shortPitchName(pitchType) {
  const names = {
    Fastball: "Fastball",
    FourSeamFastBall: "4-Seam",
    TwoSeamFastBall: "2-Seam",
    Sinker: "Sinker",
    Slider: "Slider",
    Sweeper: "Sweeper",
    Curveball: "Curveball",
    ChangeUp: "Changeup",
    Cutter: "Cutter",
    Splitter: "Splitter",
  };
  return names[pitchType] || pitchType || "Pitch";
}

function topDriverChips(pitcher, limit = 6) {
  const pct = state.percentiles.get(pitcher.slug);
  return activeHeadlineMetrics()
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

function availablePlayerYears(pitcher) {
  const years = state.allPitchers
    .filter((candidate) => candidate.slug === pitcher.slug)
    .map((candidate) => candidate.year);
  return [...new Set(years)].sort((a, b) => b - a);
}

function renderYearSelect(years = state.availableYears) {
  return `
    <select class="select-box year-select" aria-label="Select season">
      ${years.map((year) => `<option value="${year}" ${year === state.year ? "selected" : ""}>${year}</option>`).join("")}
    </select>
  `;
}

function teamBadge(pitcher, size = "") {
  const team = pitcher.team || "";
  const logo = team ? `logos/${escapeHtml(team)}.png` : "";
  return `
    <div class="team-logo ${pitcher.teamClass} ${size}" style="${teamStyle(team)}" title="${escapeHtml(formatTeamName(team))}">
      ${logo ? `<img src="${logo}" alt="" onload="this.parentElement.classList.add('has-logo')" onerror="this.remove()">` : ""}
      <span>${escapeHtml(shortTeam(team || pitcher.initials))}</span>
    </div>
  `;
}

function getMetric(key) {
  return ALL_METRICS.find((metric) => metric.key === key) || STUFF_METRIC;
}

function compareMetric(a, b, direction) {
  const aOk = Number.isFinite(a);
  const bOk = Number.isFinite(b);
  if (!aOk && !bOk) return 0;
  if (!aOk) return 1;
  if (!bOk) return -1;
  return direction * (a - b);
}

function formatMetric(value, fmt) {
  if (!Number.isFinite(value)) return "--";
  if (fmt === "decimal") return value.toFixed(3);
  if (fmt === "mph") return value.toFixed(1);
  if (fmt === "inch") return value.toFixed(1);
  if (fmt === "feet") return value.toFixed(2);
  if (fmt === "pct") return `${value.toFixed(1)}%`;
  if (fmt === "number") return value.toFixed(0);
  return String(value);
}

function formatSigned(value) {
  if (!Number.isFinite(value)) return "--";
  return `${value >= 0 ? "+" : ""}${value.toFixed(1)}`;
}

function formatDriverFeatureValue(pitch, key) {
  if (key === "ModelBase") return "model";
  const value = Number(pitch.features?.[key]);
  if (!Number.isFinite(value)) return "--";
  if (key === "RelSpeed") return `${value.toFixed(1)} mph`;
  if (key === "SpinRate") return `${value.toFixed(0)} rpm`;
  if (key === "RelHeight" || key === "Extension") return `${value.toFixed(2)} ft`;
  if (key === "HorzRelAngle" || key === "VAA") return `${value.toFixed(1)} deg`;
  return `${value.toFixed(1)} in`;
}

function displayName(name) {
  const [last, first] = String(name).split(",").map((part) => part.trim());
  return first ? `${first} ${last}` : name;
}

function shortTeam(team) {
  const cleaned = String(team || "").replace(/_/g, " ");
  const parts = cleaned.split(/\s+/).filter(Boolean);
  if (parts.length === 1) return parts[0].slice(0, 3).toUpperCase();
  return parts.map((part) => part[0]).join("").slice(0, 3).toUpperCase();
}

function formatTeamName(team) {
  const code = String(team || "").trim();
  if (!code) return "Team";
  if (TEAM_CODE_NAMES[code]) return TEAM_CODE_NAMES[code];

  const [schoolCode, mascotCode] = code.split("_");
  const school = SCHOOL_NAMES[schoolCode] || titleCaseCode(schoolCode);
  const mascot = MASCOT_NAMES[mascotCode] || titleCaseCode(mascotCode);
  return mascot ? `${school} ${mascot}` : school;
}

function titleCaseCode(value) {
  return String(value || "")
    .replace(/[0-9]+$/g, "")
    .split(/[_\s-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1).toLowerCase())
    .join(" ");
}

function teamStyle(team) {
  const palettes = [
    ["#c63d3d", "#14395d"],
    ["#1f5f98", "#10243e"],
    ["#27966f", "#10243e"],
    ["#6b55b8", "#10243e"],
    ["#f0a23a", "#14395d"],
    ["#bf4f90", "#10243e"],
    ["#8b1f2d", "#d8b34a"],
    ["#0f6048", "#d8b34a"],
  ];
  const text = String(team || "team");
  let hash = 0;
  for (let index = 0; index < text.length; index += 1) {
    hash = (hash * 31 + text.charCodeAt(index)) >>> 0;
  }
  const [primary, secondary] = palettes[hash % palettes.length];
  return `--team-a:${primary};--team-b:${secondary};`;
}

function slugify(name) {
  return String(name)
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}
