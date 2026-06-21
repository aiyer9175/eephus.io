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

// metric key -> data/glossary.json slug, where one exists. Keyed centrally so
// the duplicated shape/outcome arrays stay in sync. stuff_plus is deliberately
// NOT mapped: CollegeSavant's Stuff+ is a college TrackMan model, distinct from
// the MLB "Stuff grade+" the glossary defines, so it gets its own entry later.
const GL_SLUGS = {
  barrel_pct: "barrel_pct", hard_hit_pct: "hard_hit_pct", k_pct: "k_pct",
  bb_pct: "bb_pct", chase_pct: "chase_pct", whiff_pct: "whiff_pct",
  avg_extension: "extension", average_exit_velocity: "exit_velocity",
};
// Render a metric label, wrapped as a glossary term span when a slug exists so
// EEPHUS_GL.wire() attaches the site tooltip. HTML-safe; do not re-escape.
function glLabel(metric) {
  const text = escapeHtml(metric ? metric.label : "");
  const slug = metric && GL_SLUGS[metric.key];
  return slug ? `<span class="g-term" data-gl="${slug}">${text}</span>` : text;
}

const LEADERBOARD_LIMIT = 300;

const PITCHER_HOME_WIDGET_METRICS = [
  { key: "cs_plus", label: "CS+ (pro profile)" },
  { key: "stuff_plus", label: "Average Stuff+" },
  { key: "avg_fastball_velo", label: "Fastball Velo" },
  { key: "swinging_strike_pct", label: "SwStr %" },
  { key: "k_pct", label: "K %" },
  { key: "chase_pct", label: "Chase %" },
];

// Section hub on the home page: orient the reader to every CollegeSavant view.
const PITCHER_HOME_SECTIONS = [
  { route: "leaders", title: "Pitcher Leaderboard", note: "Every tracked arm, sortable across Stuff+, velo, whiffs, and CS+, with team and qualified filters." },
  { route: "teams", title: "Team Tendencies", note: "Which college staffs throw the hardest, miss the most bats, and run the best team CS+." },
  { route: "projections", title: "Pro Projections", note: "Each arm's projected Single-A K% / BB%, the matched-pair method, and its honest backtest." },
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
  MIN_GOL: "Minnesota Gophers",
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

// ---- CS+ : the college pitcher tracked-skill index (eephus "+" family) ------
// Pool-anchored z-average on the 100 + 10*z convention (100 = cohort average,
// +10 = one standard deviation better), same as PROSPX SC+. Two balanced skill
// families so neither outvotes the other. Components present vary by year
// (shape-only years carry no swinging-strike / chase); absent parts drop out.
// COLLEGE-RELATIVE index, NOT a Single-A projection (stuff in particular does
// not translate to pro outcomes in our matched data).
// Declared before init() runs so computeCSPlus never hits the const's dead zone.
const CSPLUS_GROUPS = [
  { name: "stuff & whiffs", parts: [
    { key: "stuff_plus", dir: 1 },
    { key: "swinging_strike_pct", dir: 1 },
    { key: "chase_pct", dir: 1 },
  ] },
  { name: "contact suppression", parts: [
    { key: "barrel_pct", dir: -1 },
    { key: "hard_hit_pct", dir: -1 },
    { key: "xwoba_against", dir: -1 },
  ] },
];

function meanStd(values) {
  const v = values.filter(Number.isFinite);
  if (!v.length) return [0, 1];
  const m = v.reduce((a, b) => a + b, 0) / v.length;
  const sd = Math.sqrt(v.reduce((a, b) => a + (b - m) * (b - m), 0) / v.length);
  return [m, sd || 1];
}

function computeCSPlus(pitchers) {
  const stats = {};
  for (const group of CSPLUS_GROUPS) {
    for (const part of group.parts) {
      if (!stats[part.key]) stats[part.key] = meanStd(pitchers.map((p) => p[part.key]));
    }
  }
  const out = new Map();
  for (const pitcher of pitchers) {
    const groupZ = [];
    for (const group of CSPLUS_GROUPS) {
      const zs = [];
      for (const part of group.parts) {
        const value = pitcher[part.key];
        if (!Number.isFinite(value)) continue;
        const [m, sd] = stats[part.key];
        zs.push(part.dir * (value - m) / sd);
      }
      if (zs.length) groupZ.push(zs.reduce((a, b) => a + b, 0) / zs.length);
    }
    if (!groupZ.length) { out.set(pitcher.slug, null); continue; }
    const avgZ = groupZ.reduce((a, b) => a + b, 0) / groupZ.length;
    out.set(pitcher.slug, Math.round(Math.max(40, Math.min(160, 100 + 10 * avgZ))));
  }
  return out;
}

// Pill markup for a "+" index, matching the site is-pos / is-neg thresholds.
function plusPill(value, label) {
  if (!Number.isFinite(value)) return "";
  const cls = value >= 110 ? "is-pos" : value <= 90 ? "is-neg" : "";
  const tip = `${label} ${value} - tracked-skill index, 100 = ${state.year} college pitcher average, +10 = one standard deviation better. College-relative, not a Single-A projection.`;
  return `<span class="cs-plus-pill ${cls}" title="${escapeHtml(tip)}">${escapeHtml(label)} ${value}</span>`;
}

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
  state.csPlus = computeCSPlus(state.pitchers);
  state.pitchPercentiles = computePitchPercentiles(state.pitches);
  if (state.sortKey !== "cs_plus" && !activeHeadlineMetrics().some((metric) => metric.key === state.sortKey)) {
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
      // No 0% -> 99th special case: a 0% barrel/hard-hit rate off a tiny batted-
      // ball sample is not "elite," and the normal pool rank already places a
      // true 0% near the top while correctly tying the many pitchers who share
      // it (percentileFromPool handles ties) instead of crowning them all 99th.
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
    afterRender();
    return;
  }
  if (hash.startsWith("#/leaders/")) {
    const key = hash.replace("#/leaders/", "").split("/")[0];
    if (key === "cs_plus" || activeHeadlineMetrics().some((metric) => metric.key === key)) state.sortKey = key;
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

// Light up the site glossary tooltips on any [data-gl] term spans the view
// emitted (no-op if eephus-gl.js is absent).
function afterRender() {
  if (window.EEPHUS_GL && window.EEPHUS_GL.wire) window.EEPHUS_GL.wire(app);
}

function updateNav(hash) {
  document.querySelectorAll("[data-route]").forEach((link) => {
    const route = link.getAttribute("href");
    link.classList.toggle("is-active", route === hash || (hash === "#/" && route === "#/"));
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
  const hub = PITCHER_HOME_SECTIONS.map((s) => {
    const href = s.route === "leaders" ? `#/leaders/stuff_plus/${state.year}` : `#/${s.route}`;
    return `<a class="hub-card" href="${href}">
      <strong>${s.title}</strong>
      <span class="hub-note">${s.note}</span>
      <span class="hub-go">Open</span>
    </a>`;
  }).join("");
  app.innerHTML = `
    <section class="toolbar home-toolbar">${renderYearSelect()}</section>

    <section class="home-intro">
      <h1>CollegeSavant - Pitchers</h1>
      <p>Tracked pitch shapes, velocity, and whiffs, a pool-anchored CS+ index, and a college-to-Single-A projection for the ${state.year} college dataset.</p>
    </section>

    <section class="hub-grid">${hub}</section>

    <div class="panel-title" style="margin-top:20px;"><span>Top of the ${state.year} class</span><span>leaders by the metrics that travel to pro ball</span></div>
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
        <span>${glLabel(metric)}</span>
        <a href="#/leaders/${metric.key}/${state.year}">View All</a>
      </div>
      <div class="widget-list">
        ${rows.map((pitcher, index) => `
          <a class="widget-row" href="#/player/${pitcher.year}/${pitcher.slug}">
            <span class="widget-rank">${index + 1}</span>
            <span class="widget-name">${escapeHtml(displayName(pitcher.pitcher_name))}</span>
            <span class="widget-team">${pitcher.team ? `<img class="widget-logo" src="logos/${escapeHtml(pitcher.team)}.png" alt="" loading="lazy" onerror="this.remove()">` : ""}${escapeHtml(formatTeamName(pitcher.team))}</span>
            <strong>${metric.key === "cs_plus" ? Math.round(state.csPlus && state.csPlus.get(pitcher.slug)) : formatMetric(pitcher[metric.key], metric.fmt)}</strong>
          </a>
        `).join("")}
      </div>
    </article>
  `;
}

function topRowsForMetric(metric) {
  const direction = metric.higherBetter ? -1 : 1;
  if (metric.key === "cs_plus") {
    return state.pitchers
      .filter((pitcher) => Number.isFinite(state.csPlus && state.csPlus.get(pitcher.slug)))
      .sort((a, b) => state.csPlus.get(b.slug) - state.csPlus.get(a.slug));
  }
  return state.pitchers
    .filter((pitcher) => Number.isFinite(pitcher[metric.key]))
    .sort((a, b) => compareMetric(a[metric.key], b[metric.key], direction));
}

// Sortable stat columns on the pitcher leaderboard. For pitchers, more chase and
// more swinging strikes are good while contact-allowed metrics are bad, so
// higherBetter is set per column (it picks the natural first-click direction).
const LB_COLUMNS = [
  { key: "cs_plus", label: "CS+", fmt: "plus", higherBetter: true },
  { key: "stuff_plus", label: "Stuff+", fmt: "plus", higherBetter: true },
  { key: "avg_fastball_velo", label: "FB Velo", fmt: "mph", higherBetter: true },
  { key: "avg_ivb", label: "IVB", fmt: "in", higherBetter: true },
  { key: "swinging_strike_pct", label: "SwStr%", fmt: "pct", higherBetter: true, gl: "whiff_pct" },
  { key: "chase_pct", label: "Chase%", fmt: "pct", higherBetter: true, gl: "chase_pct" },
  { key: "z_contact_pct", label: "Z-Con%", fmt: "pct", higherBetter: false },
  { key: "k_pct", label: "K%", fmt: "pct", higherBetter: true, gl: "k_pct" },
  { key: "bb_pct", label: "BB%", fmt: "pct", higherBetter: false, gl: "bb_pct" },
  { key: "xwoba_against", label: "xwOBA", fmt: "dec", higherBetter: false },
  { key: "barrel_pct", label: "Barrel%", fmt: "pct", higherBetter: false, gl: "barrel_pct" },
  { key: "hard_hit_pct", label: "HardHit%", fmt: "pct", higherBetter: false, gl: "hard_hit_pct" },
];

function lbFmt(fmt, v) {
  if (v == null || Number.isNaN(v)) return " - ";
  if (fmt === "plus") return String(Math.round(v));
  if (fmt === "mph" || fmt === "in") return v.toFixed(1);
  if (fmt === "dec") return v.toFixed(3).replace(/^0(?=\.)/, "");
  return v.toFixed(1) + "%";
}

function renderLeaderboard() {
  const col = LB_COLUMNS.find((c) => c.key === state.sortKey) || LB_COLUMNS[0];
  state.sortKey = col.key;
  const dir = state.sortDir != null ? state.sortDir : (col.higherBetter ? -1 : 1);
  state.sortDir = dir;
  const minPitch = state.minPitch || 0;
  const teamF = state.teamFilter || "all";
  const q = state.query.toLowerCase();
  const filtered = state.pitchers.filter((p) =>
    p.pitcher_name.toLowerCase().includes(q) &&
    (minPitch <= 0 || (p.pitch_count || 0) >= minPitch) &&
    (teamF === "all" || p.team === teamF));
  filtered.sort((a, b) => {
    const av = sortVal(a, state.sortKey), bv = sortVal(b, state.sortKey);
    const an = av == null || Number.isNaN(av), bn = bv == null || Number.isNaN(bv);
    if (an && bn) return 0;
    if (an) return 1;
    if (bn) return -1;
    return dir * (av - bv);
  });
  const visible = filtered.slice(0, LEADERBOARD_LIMIT);
  const teams = [...new Set(state.pitchers.map((p) => p.team).filter(Boolean))]
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
    const logo = p.team ? `<img class="tt-logo" src="logos/${escapeHtml(p.team)}.png" alt="" loading="lazy" onerror="this.remove()">` : "";
    return `<tr><td class="tt-rank">${i + 1}</td>
      <td class="tt-team">${logo}<a class="proj-name" href="#/player/${p.year}/${p.slug}">${escapeHtml(displayName(p.pitcher_name))}</a><span class="tt-n">${escapeHtml(formatTeamName(p.team))}</span></td>
      ${cells}</tr>`;
  }).join("");
  app.innerHTML = `
    <section class="toolbar">
      <input class="search-box" type="search" placeholder="Search pitcher" value="${escapeHtml(state.query)}" aria-label="Search pitcher">
      ${renderYearSelect()}
      <select class="select-box" data-team-filter aria-label="Filter by team">
        <option value="all">All teams</option>
        ${teams.map((t) => `<option value="${escapeHtml(t)}" ${t === teamF ? "selected" : ""}>${escapeHtml(formatTeamName(t))}</option>`).join("")}
      </select>
      <label class="lb-pa">Min pitches <input type="number" min="0" step="50" value="${minPitch}" data-min-pitch></label>
      <button class="control-button" type="button" data-reset>Reset</button>
    </section>
    <p class="note-line">${filtered.length.toLocaleString()} pitcher${filtered.length === 1 ? "" : "s"}${minPitch > 0 ? ` with ${minPitch}+ pitches` : ""}${teamF !== "all" ? ` on ${escapeHtml(formatTeamName(teamF))}` : ""}, ${state.year}. Click any column header to sort.${filtered.length > visible.length ? ` Showing the top ${visible.length}.` : ""}</p>
    <section class="leaderboard tt-board"><div class="tt-scroll"><table class="tt-table">
      <thead><tr><th class="tt-rank">#</th><th class="tt-team">Pitcher</th>${head}</tr></thead>
      <tbody>${body || `<tr><td colspan="${LB_COLUMNS.length + 2}" class="note-line">No pitchers match these filters.</td></tr>`}</tbody>
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
  const mp = app.querySelector("[data-min-pitch]");
  if (mp) mp.addEventListener("change", (e) => { state.minPitch = Number(e.target.value) || 0; renderLeaderboard(); });
  const ys = app.querySelector(".year-select");
  if (ys) ys.addEventListener("change", (e) => { setActiveYear(e.target.value); renderLeaderboard(); });
  const rb = app.querySelector("[data-reset]");
  if (rb) rb.addEventListener("click", () => {
    state.query = ""; state.minPitch = 0; state.teamFilter = "all"; state.sortKey = "stuff_plus"; state.sortDir = null;
    renderLeaderboard();
  });
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

// ---- College Team Tendencies (pitching staffs) -----------------------------
// Team-level aggregates over the year cohort: which college staffs throw the
// hardest, miss the most bats, run the best team CS+. Pure aggregation over the
// tracked data we already hold, grouped by the team code on each pitcher row.
const TEAM_TENDENCY_METRICS = [
  { key: "cs_plus", label: "Team CS+", fmt: "plus", agg: "mean" },
  { key: "stuff_plus", label: "Stuff+", fmt: "num", agg: "mean" },
  { key: "avg_fastball_velo", label: "FB Velo", fmt: "mph", agg: "mean" },
  { key: "swinging_strike_pct", label: "SwStr %", fmt: "pct", agg: "mean" },
  { key: "chase_pct", label: "Chase %", fmt: "pct", agg: "mean" },
  { key: "k_pct", label: "K %", fmt: "pct", agg: "mean" },
  { key: "bb_pct", label: "BB %", fmt: "pct", agg: "mean" },
  { key: "barrel_pct", label: "Barrel% allowed", fmt: "pct", agg: "mean" },
  { key: "hard_hit_pct", label: "HardHit% allowed", fmt: "pct", agg: "mean" },
];
const TEAM_MIN_ARMS = 3;

function teamMetricValue(pitchers, m) {
  if (m.key === "cs_plus") {
    const vs = pitchers.map((p) => state.csPlus && state.csPlus.get(p.slug)).filter(Number.isFinite);
    return vs.length ? vs.reduce((a, b) => a + b, 0) / vs.length : null;
  }
  const vs = pitchers.map((p) => p[m.key]).filter(Number.isFinite);
  if (!vs.length) return null;
  return m.agg === "max" ? Math.max(...vs) : vs.reduce((a, b) => a + b, 0) / vs.length;
}

function computeTeamTendencies(pitchers) {
  const byTeam = new Map();
  for (const p of pitchers) {
    const t = p.team || "";
    if (!t) continue;
    if (!byTeam.has(t)) byTeam.set(t, []);
    byTeam.get(t).push(p);
  }
  const rows = [];
  for (const [team, ps] of byTeam) {
    if (ps.length < TEAM_MIN_ARMS) continue;
    const agg = {};
    for (const m of TEAM_TENDENCY_METRICS) agg[m.key] = teamMetricValue(ps, m);
    rows.push({ team, n: ps.length, agg });
  }
  return rows;
}

// ---- Draft Prospects section (the reverse direction) -----------------------
// Draft-eligible pitchers carried INTO CollegeSavant by the conventional college
// box scores we already hold, including prospects with no tracking. Box-score
// based and FV-ranked, filterable by draft year.
function renderProspects() {
  const P = (window.CS_DRAFT_PROSPECTS && window.CS_DRAFT_PROSPECTS.pitchers) || [];
  const years = [...new Set(P.map((x) => x.year).filter(Boolean))].sort((a, b) => b - a);
  const yf = state.prospectYear != null ? state.prospectYear : (years[0] || "all");
  const list = P.filter((x) => yf === "all" || x.year === yf);
  const d2 = (x) => (x == null ? " - " : x.toFixed(2));
  const body = list.map((x, i) => {
    const b = x.box || {};
    const wl = (b.w != null || b.l != null) ? `${b.w == null ? 0 : b.w}-${b.l == null ? 0 : b.l}` : " - ";
    return `<tr><td class="tt-rank">${i + 1}</td>
      <td class="tt-team"><strong>${escapeHtml(x.name || "")}</strong><span class="tt-n">${escapeHtml(x.school || "")}${x.pos ? " · " + escapeHtml(x.pos) : ""}</span></td>
      <td class="tt-col">${x.fv != null ? Math.ceil(x.fv) : " - "}</td>
      <td class="tt-col">${x.year || " - "}</td>
      <td class="tt-col">${b.ip != null ? b.ip.toFixed(1) : " - "}</td>
      <td class="tt-col">${d2(b.era)}</td><td class="tt-col">${d2(b.fip)}</td>
      <td class="tt-col">${d2(b.k_per_9)}</td><td class="tt-col">${d2(b.bb_per_9)}</td>
      <td class="tt-col">${wl}</td></tr>`;
  }).join("");
  app.innerHTML = `
    <section class="toolbar">
      <select class="select-box" data-prospect-year aria-label="Draft year">
        <option value="all" ${yf === "all" ? "selected" : ""}>All draft years</option>
        ${years.map((y) => `<option value="${y}" ${y === yf ? "selected" : ""}>${y} draft</option>`).join("")}
      </select>
    </section>
    <div class="panel-title"><span>Draft Prospects in college</span><span>${list.length} pitching prospect${list.length === 1 ? "" : "s"} · conventional college stats, FV-ranked</span></div>
    <p class="trans-note">Draft-eligible pitchers carried into CollegeSavant by the college box scores we hold (FanGraphs / NCAA), including prospects with no tracking. FV is the consensus board grade, rounded up. This board is box-score based; the tracked CS+ and pitch-shape views cover only players with tracking data.</p>
    <section class="leaderboard tt-board"><div class="tt-scroll"><table class="tt-table">
      <thead><tr><th class="tt-rank">#</th><th class="tt-team">Prospect</th><th class="tt-col">FV</th><th class="tt-col">Yr</th><th class="tt-col">IP</th><th class="tt-col">ERA</th><th class="tt-col">FIP</th><th class="tt-col">K/9</th><th class="tt-col">BB/9</th><th class="tt-col">W-L</th></tr></thead>
      <tbody>${body || `<tr><td colspan="10" class="note-line">No draft prospects with college stats for this year.</td></tr>`}</tbody>
    </table></div></section>`;
  const ys = app.querySelector("[data-prospect-year]");
  if (ys) ys.addEventListener("change", (e) => {
    state.prospectYear = e.target.value === "all" ? "all" : Number(e.target.value);
    renderProspects();
  });
}

// ---- College -> Single-A Projections (pitchers) ----------------------------
// Mirror of the hitter Pro Projections page: the methodology, the leave-one-out
// backtest, and a board of every pitcher's projected Single-A K% / BB% (the only
// two arms-side rates the matched-pair model carries), ranked by CS+.
function renderProjections() {
  const E = (window.CS_TRANSLATION && window.CS_TRANSLATION.eval) || {};
  const T = (window.CS_TRANSLATION && window.CS_TRANSLATION.translations) || {};
  const accRows = [["Proj Single-A K%", "pit_k"], ["Proj Single-A BB%", "pit_bb"]]
    .map(([label, k]) => {
      const f = E[k];
      if (!f) return "";
      const cov = f.coverage != null ? Math.round(f.coverage * 100) + "%" : " - ";
      const flag = (f.r2 != null && f.r2 < 0.10) ? ` <span class="trans-flag">low signal</span>` : "";
      return `<tr><td class="tt-team">${label}${flag}</td>
        <td class="tt-col">${f.r2 != null ? f.r2.toFixed(2) : " - "}</td>
        <td class="tt-col">±${f.band_sd ?? " - "}</td>
        <td class="tt-col">${f.mae ?? " - "}</td>
        <td class="tt-col">${cov}</td><td class="tt-col">${f.n ?? " - "}</td></tr>`;
    }).join("");
  const pband = (b) => b == null ? " - " : b.exp.toFixed(1) + "%";
  const list = state.pitchers
    .map((p) => ({ p, t: T[p.slug], cs: state.csPlus && state.csPlus.get(p.slug) }))
    .filter((x) => x.t && x.t.single_a)
    .sort((a, b) => (b.cs ?? -Infinity) - (a.cs ?? -Infinity))
    .slice(0, LEADERBOARD_LIMIT);
  const body = list.map((x, i) => {
    const sa = x.t.single_a;
    const logo = x.p.team ? `<img class="tt-logo" src="logos/${escapeHtml(x.p.team)}.png" alt="" loading="lazy" onerror="this.remove()">` : "";
    return `<tr><td class="tt-rank">${i + 1}</td>
      <td class="tt-team">${logo}<a class="proj-name" href="#/player/${x.p.year}/${x.p.slug}">${escapeHtml(displayName(x.p.pitcher_name))}</a></td>
      <td class="tt-col">${plusPill(x.cs, "CS+")}</td>
      <td class="tt-col">${pband(sa.k_pct)}</td>
      <td class="tt-col">${pband(sa.bb_pct)}</td></tr>`;
  }).join("");
  app.innerHTML = `
    <section class="toolbar">${renderYearSelect()}</section>
    <div class="panel-title"><span>How the projection works</span><span>college-to-Single-A statistical translation</span></div>
    <ol class="proj-method">
      <li><strong>Matched pairs.</strong> We take college pitchers who later reached Single-A, pair each one's college rate with the Single-A rate they actually posted, and fit how the two relate. Strikeout and walk rates are read from K/9 and BB/9 over batters faced.</li>
      <li><strong>Regression to the mean.</strong> A college rate is pulled toward the Single-A average by an amount set from how strongly the two levels track in the data, a fitted slope shrunk for sample size. An extreme college number is moderated, never copied straight across.</li>
      <li><strong>Honest bands.</strong> The P10-P90 band is the spread of the model's own misses on arms it was not fit on (leave-one-out). Coverage near 80% in the table below means the band is sized to reality, not for show.</li>
      <li><strong>What to trust.</strong> Strikeout rate carries the signal here; walk rate largely washes out to the Single-A mean and is flagged. Read it as context, not a forecast.</li>
      <li><strong>What it does not do.</strong> No schedule-strength or park adjustment, since no college conference or park table is held. Stuff+, CS+, and the tracked pitch shapes describe college stuff; they are not a scouting Future Value, which the tracked data does not predict.</li>
    </ol>
    <div class="panel-title" style="margin-top:18px;"><span class="g-term" data-gl="single_a_equivalent">How accurate is this</span><span>leave-one-out backtest on the matched college-to-Single-A pairs</span></div>
    <section class="leaderboard tt-board"><div class="tt-scroll"><table class="tt-table">
      <thead><tr><th class="tt-team">Projection</th><th class="tt-col">r²</th><th class="tt-col">±band</th><th class="tt-col">MAE</th><th class="tt-col">P10-P90 cover</th><th class="tt-col">n pairs</th></tr></thead>
      <tbody>${accRows || `<tr><td colspan="6" class="note-line">No backtest on file.</td></tr>`}</tbody>
    </table></div></section>
    <div class="panel-title" style="margin-top:18px;"><span>Projected Single-A board</span><span>${list.length} pitchers with a projection · ranked by CS+ (pro profile)</span></div>
    <section class="leaderboard tt-board"><div class="tt-scroll"><table class="tt-table">
      <thead><tr><th class="tt-rank">#</th><th class="tt-team">Pitcher</th><th class="tt-col">CS+</th><th class="tt-col">Proj A K%</th><th class="tt-col">Proj A BB%</th></tr></thead>
      <tbody>${body || `<tr><td colspan="5" class="note-line">No projections for this year.</td></tr>`}</tbody>
    </table></div></section>`;
  const ys = app.querySelector(".year-select");
  if (ys) ys.addEventListener("change", (e) => { setActiveYear(e.target.value); renderProjections(); });
}

function renderTeams() {
  const sortKey = TEAM_TENDENCY_METRICS.some((m) => m.key === state.teamSort) ? state.teamSort : "cs_plus";
  const rows = computeTeamTendencies(state.pitchers)
    .sort((a, b) => (b.agg[sortKey] ?? -Infinity) - (a.agg[sortKey] ?? -Infinity));
  const fmtVal = (m, v) => {
    if (v == null) return " - ";
    if (m.fmt === "plus" || m.fmt === "num") return String(Math.round(v));
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
    return `<tr><td class="tt-rank">${i + 1}</td>
      <td class="tt-team"><span>${escapeHtml(formatTeamName(r.team))}</span><span class="tt-n">${r.n} arms</span></td>
      ${cells}</tr>`;
  }).join("");
  app.innerHTML = `
    <section class="toolbar">
      ${renderYearSelect()}
      <select class="select-box" data-team-sort aria-label="Rank staffs by">
        ${TEAM_TENDENCY_METRICS.map((m) => `<option value="${m.key}" ${m.key === sortKey ? "selected" : ""}>Rank by ${m.label}</option>`).join("")}
      </select>
    </section>
    <p class="note-line">College pitching-staff tendencies for ${state.year}: every staff with at least ${TEAM_MIN_ARMS} tracked arms, aggregated across its pitchers. Team CS+ is the mean of its arms' CS+ (100 = the college average).</p>
    <section class="leaderboard tt-board">
      <div class="tt-scroll"><table class="tt-table">
        <thead><tr><th class="tt-rank">#</th><th class="tt-team">Staff</th>${head}</tr></thead>
        <tbody>${body || `<tr><td colspan="${TEAM_TENDENCY_METRICS.length + 2}" class="note-line">No staffs with enough tracked arms this year.</td></tr>`}</tbody>
      </table></div>
    </section>`;
  const sel = app.querySelector("[data-team-sort]");
  if (sel) sel.addEventListener("change", (e) => { state.teamSort = e.target.value; renderTeams(); });
  const ys = app.querySelector(".year-select");
  if (ys) ys.addEventListener("change", (e) => { setActiveYear(e.target.value); renderTeams(); });
}

// College -> Single-A projection block. Reads window.CS_TRANSLATION by slug and
// shows projected Single-A K% / BB% (expected + P10-P90 band). BB% carries no
// signal in the matched data, so it is flagged; stuff/shapes are descriptive
// only (the CS+ index), never an outcome forecast. Empty when no translation.
function renderTranslation(pitcher) {
  const T = window.CS_TRANSLATION && window.CS_TRANSLATION.translations;
  const t = T && T[pitcher.slug];
  if (!t || !t.single_a) return "";
  const sa = t.single_a;
  const pct = (x) => (x == null ? "--" : x.toFixed(1) + "%");
  const row = (label, b, flag) => {
    if (!b) return "";
    const tag = flag ? ` <span class="trans-flag">${escapeHtml(flag)}</span>` : "";
    return `<div class="trans-row">
      <span class="trans-label">${label}${tag}</span>
      <span class="trans-val">${pct(b.exp)}</span>
      <span class="trans-band">${pct(b.lo)} – ${pct(b.hi)}</span>
    </div>`;
  };
  const rows = [
    row("Proj. Single-A K%", sa.k_pct, null),
    row("Proj. Single-A BB%", sa.bb_pct, sa.bb_pct && sa.bb_pct.low_confidence ? "low confidence" : null),
  ].join("");
  if (!rows.trim()) return "";
  return `
    <section class="panel trans-panel">
      <div class="panel-title">
        <span class="g-term" data-gl="single_a_equivalent">Projected Single-A</span>
        <span>expected · P10-P90 band</span>
      </div>
      <div class="trans-grid">
        <div class="trans-head"><span></span><span>Expected</span><span>P10 – P90</span></div>
        ${rows}
      </div>
      <p class="trans-note">Matched-pair projection from this college K% / BB% to a Single-A
      expectation, fit on our own college-to-Single-A pairs. Not adjusted for schedule
      strength or park. The band is the P10-P90 range. K% is moderately reliable; BB%
      carries little signal yet. Stuff+ and pitch shapes stay descriptive (the CS+ index),
      not a pro outcome forecast.</p>
    </section>`;
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
          <div class="profile-team">${teamBadge(pitcher, "mini")}<span>${escapeHtml(formatTeamName(pitcher.team))}</span>${plusPill(state.csPlus && state.csPlus.get(pitcher.slug), "CS+")}${renderYearSelect(availablePlayerYears(pitcher))}</div>
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

      ${renderTranslation(pitcher)}

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

// Pitch-shape payloads load on demand: pitch_shape_data_2024.js is 38MB and
// was the single heaviest asset on the site when it shipped at boot. The
// detail panel renders a loading note, the script injects once, and the
// hash-driven render() repaints when it lands.
const _shapeLoadState = {};   // year -> "loading" | "ready" | "failed"
function ensurePitchShapes(year) {
  if (window[`PITCH_SHAPES_${year}`]) return true;
  if (_shapeLoadState[year] === "loading" || _shapeLoadState[year] === "failed") return false;
  _shapeLoadState[year] = "loading";
  const s = document.createElement("script");
  s.src = `pitch_shape_data_${year}.js`;
  s.onload = () => { _shapeLoadState[year] = "ready"; render(); };
  s.onerror = () => { _shapeLoadState[year] = "failed"; render(); };
  document.head.appendChild(s);
  return false;
}

function renderPitchShapePlot(pitcher) {
  if (!hasPitchByPitchOutcomes(pitcher.year)) return "";

  if (!ensurePitchShapes(pitcher.year)) {
    return _shapeLoadState[pitcher.year] === "failed"
      ? `<div class="chart-empty">Pitch-shape data unavailable for ${pitcher.year}.</div>`
      : `<div class="chart-empty">Loading ${pitcher.year} pitch shapes&hellip;</div>`;
  }

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
        <div class="slider-label">${glLabel(metric)}</div>
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
  if (key === "cs_plus") return { key: "cs_plus", label: "CS+", fmt: "number", higherBetter: true };
  return ALL_METRICS.find((metric) => metric.key === key) || STUFF_METRIC;
}

// Sort value for a key, including the computed CS+ (not a column on the row).
function sortVal(pitcher, key) {
  return key === "cs_plus" ? (state.csPlus && state.csPlus.get(pitcher.slug)) : pitcher[key];
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
