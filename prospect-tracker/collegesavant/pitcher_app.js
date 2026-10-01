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
  { route: "prospects", title: "Draft Prospects", note: "Draft-eligible college arms carried in by the box scores we hold, FV-ranked with a projected Single-A line." },
  { route: "projections", title: "MiLB Projections", note: "Each arm's projected Single-A K% / BB%, the matched-pair method, and its leave-one-out backtest." },
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

// Only these team codes have a logo PNG in collegesavant/logos/; gate <img>
// emission on this set so non-listed schools do not fire 404 image requests.
const TEAM_LOGOS = new Set([
  "ILL_ILL", "IOW_HAW", "IU", "MAR_TER", "MIC_SPA", "MIC_WOL", "MIN_GOL",
  "NEB", "NOR_CAT", "ORE_DUC", "OSU_BUC", "PEN_NIT", "PUR_BOI", "RUT_SCA",
  "SOU_TRO", "WAS_HUS",
]);

// TEAM_CODE_NAMES / SCHOOL_NAMES / MASCOT_NAMES and formatTeamName live in the
// shared team_names.js, loaded before this file.

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
    // 2026-07-29: the 40 / 160 clamp is REMOVED. It was display compression -
    // an outlier that computed 168 was shown as 160, so the printed CS+ stopped
    // being the model's number without saying so (the same class of defect the
    // KRP+ clamp removal fixed). Full true-to-model per the owner. No pitcher in
    // any shipped payload year reached a bound (2024 spans 65.2-123.3, 2025
    // 84.7-140.2, 2026 66.8-122.2), so no displayed value changes today; what
    // changes is that a future outlier will print its real index.
    out.set(pitcher.slug, Math.round(100 + 10 * avgZ));
  }
  return out;
}

// Pill markup for a "+" index, matching the site is-pos / is-neg thresholds.
function plusPill(value, label) {
  if (!Number.isFinite(value)) return "";
  const cls = value >= 110 ? "is-pos" : value <= 90 ? "is-neg" : "";
  const tip = `${label} ${value} - tracked-skill index, 100 = the ${state.year} pool average (${poolText(state.year)}), +10 = one standard deviation better. College-relative, not a Single-A projection.`;
  return `<span class="cs-plus-pill ${cls}" title="${escapeHtml(tip)}">${escapeHtml(label)} ${value}</span>`;
}

// Per-year pitch tables ride in as pitcher_pitch_data_<year>.js, each defining
// window.PITCHER_PITCH_DATA_<year>. The page ships only the small recent-season
// files (2025 + 2026); the 11.6MB 2024 table loads on demand the first time a
// view asks for that season (same injector pattern as ensurePitchShapes).
// The consts are declared before init() runs (same dead-zone rule as
// CSPLUS_GROUPS above): collectPitchRows reads them during boot.
const PITCH_DATA_YEARS = [2024, 2025, 2026];
const _pitchDataLoadState = {};   // year -> "loading" | "ready" | "failed"

function pitchRowsFor(year) {
  return window[`PITCHER_PITCH_DATA_${year}`];
}

// Every pitch row currently on the page: the per-year tables plus the legacy
// combined window.PITCHER_PITCH_DATA (still honored so older cached copies of
// pitcher_data.js and the smoke harness keep working).
function collectPitchRows() {
  let rows = window.PITCHER_PITCH_DATA || [];
  for (const year of PITCH_DATA_YEARS) {
    const yearRows = pitchRowsFor(year);
    if (Array.isArray(yearRows)) rows = rows.concat(yearRows);
  }
  return rows;
}

function pitchDataLoading(year) {
  return _pitchDataLoadState[year] === "loading";
}

// Returns true when the year's pitch rows are on the page (or the year has no
// file to fetch). Otherwise injects the year's script once and returns false;
// onload merges the rows and repaints, onerror leaves the views' empty states.
function ensurePitchData(year) {
  if (!PITCH_DATA_YEARS.includes(year) || pitchRowsFor(year)) return true;
  if (_pitchDataLoadState[year] === "loading" || _pitchDataLoadState[year] === "failed") return false;
  _pitchDataLoadState[year] = "loading";
  const s = document.createElement("script");
  s.src = `pitcher_pitch_data_${year}.js`;
  s.onload = () => {
    _pitchDataLoadState[year] = "ready";
    state.allPitches = state.allPitches.concat((pitchRowsFor(year) || []).map(normalizePitchRow));
    setActiveYear(state.year);
    render();
  };
  s.onerror = () => { _pitchDataLoadState[year] = "failed"; render(); };
  document.head.appendChild(s);
  return false;
}

function init() {
  try {
    // The pitcher payload rides in as a script tag (pitcher_data.js); if that
    // script failed to load, the page would otherwise render an empty
    // leaderboard with no hint anything went wrong (F-02).
    if (!window.PITCHER_DATA) throw new Error("pitcher_data.js is missing or failed to load");
    state.allPitchers = (window.PITCHER_DATA || []).map(normalizePitcher);
    state.allPitches = collectPitchRows().map(normalizePitchRow);
    state.availableYears = [...new Set(state.allPitchers.map((pitcher) => pitcher.year))].sort((a, b) => b - a);
    state.year = state.availableYears[0] || 2026;
    setActiveYear(yearFromHash(window.location.hash) || state.year);
    window.addEventListener("hashchange", render);
    render();
  } catch (error) {
    // Visible error state (F-02): the data payload script failed.
    app.innerHTML = `<section class="empty" role="alert"><strong>Data failed to load.</strong> Refresh to retry; if it persists the nightly build is mid-run.<br><span style="color:var(--text-tertiary)">${escapeHtml(error.message)}</span><br><br><a class="pill" href="" onclick="location.reload();return false;">Retry</a></section>`;
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

// Each season's payload is a different pool: 2024 is the national TrackMan set
// (4,400+ arms on 480+ teams), 2025 is a Big Ten slice, and 2026 is an early
// cut (a median of about 70 pitches, no K/BB or swing-decision columns). CS+
// and every percentile are z-scored within the active season, so "100" means
// that pool's average. The page opens on the newest season (owner answer
// M19-2, 2026-09-25), and the season picker and the CS+ copy name each pool:
// its scope (national, or Big Ten only when every team code is a Big Ten
// school), size, team count and median pitch count (census M03-10).
const BIG_TEN_CODES = new Set([
  "ILL_ILL", "IOW_HAW", "IU", "MAR_TER", "MIC_SPA", "MIC_WOL", "MIN_GOL", "NEB",
  "NOR_CAT", "ORE_DUC", "OSU_BUC", "PEN_NIT", "PUR_BOI", "RUT_SCA", "SOU_TRO", "WAS_HUS",
]);
// The vendored CollegeSavant files arrived with the module (2026-06-11) and
// have not been refreshed since. They carry no game dates, so the data stamp
// names the day they were received, never a games-through date.
const DATA_RECEIVED = "2026-06-11";

function yearPool(year) {
  const rows = (state.allPitchers || []).filter((p) => p.year === year);
  const teamSet = new Set(rows.map((p) => p.team).filter(Boolean));
  const scope = !teamSet.size ? "" : [...teamSet].every((t) => BIG_TEN_CODES.has(t)) ? "Big Ten only" : "national";
  const pc = rows.map((p) => Number(p.pitch_count)).filter(Number.isFinite).sort((a, b) => a - b);
  return { n: rows.length, teams: teamSet.size, scope, medPitches: pc.length ? pc[Math.floor(pc.length / 2)] : null };
}
function poolText(year) {
  const { n, teams, scope, medPitches } = yearPool(year);
  return `${scope ? `${scope} · ` : ""}${n.toLocaleString()} arm${n === 1 ? "" : "s"}`
    + `${teams ? `, ${teams} team${teams === 1 ? "" : "s"}` : ""}`
    + (medPitches != null ? `, median ${medPitches} pitches` : "");
}

// Default sample qualifier (owner answer M19-3): the active pool's median
// pitch count, shown in the Min pitches control with its number and
// changeable by the reader. state.minPitch null means "follow the pool
// median"; a season change resets it. The qualifier only filters which arms
// are listed: CS+ and every percentile stay computed against the whole pool.
function qualifier() {
  const { medPitches } = yearPool(state.year);
  if (medPitches == null) return { available: false, value: 0, median: null, isDefault: true };
  const user = state.minPitch;
  return { available: true, value: user == null ? medPitches : user, median: medPitches, isDefault: user == null };
}
function passesQualifier(p, q) {
  return !q.available || q.value <= 0 || (p.pitch_count || 0) >= q.value;
}
function qualifierControl(q) {
  if (!q.available) {
    return `<span class="lb-pa lb-pa-off">Min pitches: unavailable for ${state.year} (no pitch counts)</span>`;
  }
  return `<label class="lb-pa">Min pitches <input type="number" min="0" step="10" value="${q.value}" data-min-pitch aria-label="Minimum pitches, default the ${state.year} pool median of ${q.median}"> <span class="lb-pa-note">median ${q.median}</span></label>`;
}
function qualifierText(q) {
  if (!q.available) return `no sample qualifier: the ${state.year} pool has no pitch counts, so every arm is listed`;
  if (q.value <= 0) return `no pitch minimum (the ${state.year} pool median is ${q.median} pitches)`;
  return `${q.value}+ pitches${q.isDefault ? ` (default: the ${state.year} pool median)` : ` (the ${state.year} pool median is ${q.median})`}`;
}
function dataStamp() {
  const inSeason = state.year >= Number(DATA_RECEIVED.slice(0, 4));
  return `Data through: the CollegeSavant files received ${DATA_RECEIVED}, not refreshed since; the files carry no game dates. `
    + `The ${state.year} pool: ${poolText(state.year)}${inSeason ? `, a cut taken during the ${state.year} season` : ""}.`;
}

function setActiveYear(year) {
  const numericYear = Number(year);
  const previous = state.year;
  state.year = state.availableYears.includes(numericYear) ? numericYear : (state.availableYears[0] || numericYear);
  if (state.year !== previous) state.minPitch = null;
  ensurePitchData(state.year);
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
    // Section-aware: leaderboard (#/leaders/*) and player (#/player/*) views
    // belong to the Dashboard tab, so it lights up instead of leaving the bar blank.
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
  const hub = PITCHER_HOME_SECTIONS.map((s) => {
    const href = s.route === "leaders" ? `#/leaders/stuff_plus/${state.year}` : `#/${s.route}`;
    return `<a class="hub-card" href="${href}">
      <strong>${s.title}</strong>
      <span class="hub-note">${s.note}</span>
      <span class="hub-go">Open</span>
    </a>`;
  }).join("");
  const q = qualifier();
  app.innerHTML = `
    <section class="toolbar home-toolbar">${renderYearSelect()}${qualifierControl(q)}</section>

    <section class="home-intro">
      <h1>CollegeSavant - Pitchers</h1>
      <p>Tracked pitch shapes, velocity, and whiffs, a pool-anchored CS+ index, and a college-to-Single-A projection for the ${state.year} college dataset.</p>
      <p class="cs-stamp">${escapeHtml(dataStamp())}</p>
    </section>

    <section class="hub-grid">${hub}</section>

    <div class="panel-title" style="margin-top:20px;"><span>Top of the ${state.year} class</span><span>leaders by the metrics that travel to pro ball</span></div>
    <p class="note-line">Listed: ${escapeHtml(qualifierText(q))}. CS+ 100 = the ${state.year} pool average (${escapeHtml(poolText(state.year))}).</p>
    <section class="widget-grid">
      ${PITCHER_HOME_WIDGET_METRICS.map((item) => renderTopWidget({ ...getMetric(item.key), label: item.label }, q)).join("")}
    </section>
  `;

  app.querySelector(".year-select").addEventListener("change", (event) => {
    setActiveYear(event.target.value);
    window.location.hash = "#/";
    renderHome();
  });
  const mp = app.querySelector("[data-min-pitch]");
  if (mp) mp.addEventListener("change", (e) => { state.minPitch = Number(e.target.value) || 0; renderHome(); });
}

function renderTopWidget(metric, q = qualifier()) {
  const rows = topRowsForMetric(metric).filter((p) => passesQualifier(p, q)).slice(0, 10);
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
            <span class="widget-team">${pitcher.team && TEAM_LOGOS.has(pitcher.team) ? `<img class="widget-logo" src="logos/${escapeHtml(pitcher.team)}.png" alt="" loading="lazy" onerror="this.remove()">` : ""}${escapeHtml(formatTeamName(pitcher.team))}</span>
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
  const qual = qualifier();
  const teamF = state.teamFilter || "all";
  const q = state.query.toLowerCase();
  const filtered = state.pitchers.filter((p) =>
    p.pitcher_name.toLowerCase().includes(q) &&
    passesQualifier(p, qual) &&
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
    const logo = p.team && TEAM_LOGOS.has(p.team) ? `<img class="tt-logo" src="logos/${escapeHtml(p.team)}.png" alt="" loading="lazy" onerror="this.remove()">` : "";
    return `<tr><td class="tt-rank">${i + 1}</td>
      <td class="tt-team">${logo}<a class="proj-name" href="#/player/${p.year}/${p.slug}">${escapeHtml(displayName(p.pitcher_name))}</a><span class="tt-n">${escapeHtml(formatTeamName(p.team))}</span></td>
      ${cells}</tr>`;
  }).join("");
  app.innerHTML = `
    <section class="toolbar">
      <input class="search-box" type="search" placeholder="Search pitcher" value="${escapeHtml(state.query)}" aria-label="Search pitcher">
      ${renderYearSelect()}
      <select class="select-box" data-team-filter data-team-picker="college" aria-label="Filter by team">
        <option value="all">All teams</option>
        ${teams.map((t) => `<option value="${escapeHtml(t)}"${TEAM_LOGOS.has(t) ? ` data-logo="logos/${escapeHtml(t)}.png"` : ""} ${t === teamF ? "selected" : ""}>${escapeHtml(formatTeamName(t))}</option>`).join("")}
      </select>
      ${qualifierControl(qual)}
      <button class="control-button" type="button" data-reset>Reset</button>
      <button class="chip egfx-chip" id="cs-lb-gfx" title="Generate a shareable graphic (theme-aware, multiple formats)"><span class="egfx-chip-glyph" aria-hidden="true">&#9636;</span>Generate GFX</button>
    </section>
    <p class="note-line">${filtered.length.toLocaleString()} pitcher${filtered.length === 1 ? "" : "s"}${teamF !== "all" ? ` on ${escapeHtml(formatTeamName(teamF))}` : ""}, ${state.year}: ${escapeHtml(qualifierText(qual))}. CS+ and percentiles compare against the whole ${state.year} pool. Click any column header to sort.${filtered.length > visible.length ? ` Showing the top ${visible.length}.` : ""}</p>
    <p class="note-line cs-stamp">${escapeHtml(dataStamp())}</p>
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
    state.query = ""; state.minPitch = null; state.teamFilter = "all"; state.sortKey = "stuff_plus"; state.sortDir = null;
    renderLeaderboard();
  });
  const lbGfx = app.querySelector("#cs-lb-gfx");
  if (lbGfx) lbGfx.onclick = () => {
    if (window.EEPHUS_GFX) window.EEPHUS_GFX.open(csLeaderboardSpec(filtered, col, dir));
  };
}

// Board spec for the Generate GFX modal: the current filtered + sorted pitcher
// leaderboard as a column board (leading metric + its percentile + CS+), built
// from the SAME `filtered` array the table renders so the graphic always
// matches what's on screen. Mirrors fa.js/_faBoardSpec + projections.js.
function csLeaderboardSpec(rows, col, dir) {
  const pctOf = state.percentiles || new Map();
  const csOf = state.csPlus || new Map();
  const brows = rows.map((p, i) => {
    const v = sortVal(p, col.key);
    const pctMap = pctOf.get(p.slug) || {};
    const pctV = pctMap[col.key];
    const cs = csOf.get(p.slug);
    const csColor = Number.isFinite(cs) ? (cs >= 110 ? "green" : cs <= 90 ? "red" : "muted") : "muted";
    return { cells: [
      { t: i + 1 },
      { t: displayName(p.pitcher_name), sub: formatTeamName(p.team) || undefined },
      { t: lbFmt(col.fmt, v), c: "accent" },
      { t: Number.isFinite(pctV) ? String(Math.round(pctV)) : "-", c: "muted" },
      { t: Number.isFinite(cs) ? String(Math.round(cs)) : "-", c: csColor },
    ] };
  });
  return {
    kind: "board", module: "CollegeSavant", accentToken: "--accent-red",
    title: `CollegeSavant · ${col.label} Leaders`,
    subtitle: `${state.year} college pitchers · sorted by ${col.label}${dir < 0 ? " (high → low)" : " (low → high)"} · ${rows.length} qualified`,
    url: "eephus.io/collegesavant/pitcher_index.html", filenameBase: `eephus-collegesavant-pitchers-${col.key}`,
    caption: "college tracked-skill leaders · CollegeSavant by Joseph Gillis",
    board: { defaultCount: 25, counts: [10, 25, 50], legend: `CS+ 100 = ${state.year} pool average (${poolText(state.year)})`, columns: [
      { label: "#", frac: 0.06 },
      { label: "Pitcher", frac: 0.42 },
      { label: col.label, frac: 0.20 },
      { label: "Pctile", frac: 0.16 },
      { label: "CS+", frac: 0.16 },
    ], rows: brows },
  };
}

function _wireCsShare(pitcher, pct) {
  const btn = app.querySelector("#cs-share");
  if (!btn) return;
  btn.addEventListener("click", () => {
    if (!window.EEPHUS_HUB) return;   // openCard lives on the hub
    // Declarative since GFX slice 4: the "leaderboard-subject" template owns
    // the layout (stat-tile rail + one percentile section); this site only
    // supplies the data, formatted with this module's own formatMetric.
    // Shared wrapper (DE-DUP 2026-07-23): prefers the Generate GFX modal,
    // falls back to the legacy direct shareCard download.
    window.EEPHUS_HUB.openCard({
      template: "leaderboard-subject",
      data: {
        stats: [
          pitcher.stuff_plus != null ? { label: "Stuff+", value: formatMetric(pitcher.stuff_plus, "number") } : null,
          pitcher.avg_fastball_velo != null ? { label: "FB velo", value: formatMetric(pitcher.avg_fastball_velo, "mph") } : null,
          pitcher.xwoba_against != null ? { label: "xwOBA agn", value: formatMetric(pitcher.xwoba_against, "decimal") } : null,
        ].filter(Boolean),
        poolSize: state.pitchers.length,
        poolNoun: "pitchers",
        percentiles: activePitcherMetrics()
          .filter((m) => pitcher[m.key] != null)
          .map((m) => ({ label: m.label, value: formatMetric(pitcher[m.key], m.fmt),
            pct: pct && pct[m.key] != null ? pct[m.key] : "-" })),
      },
      module: "CollegeSavant",
      accentToken: "--accent-red",
      name: displayName(pitcher.pitcher_name),
      meta: `${formatTeamName(pitcher.team)} · ${pitcher.year} · college pitcher`,
      headshotURL: TEAM_LOGOS.has(pitcher.team) ? `logos/${pitcher.team}.png` : null,
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
const PROSPECT_COLS_PIT = [
  { key: "fv", label: "FV", get: (x) => x.fv, t: "ceil", hb: true },
  { key: "year", label: "Yr", get: (x) => x.year, t: "raw", hb: true },
  { key: "ip", label: "IP", get: (x) => x.box && x.box.ip, t: "dec1", hb: true },
  { key: "era", label: "ERA", get: (x) => x.box && x.box.era, t: "dec2", hb: false },
  { key: "fip", label: "FIP", get: (x) => x.box && x.box.fip, t: "dec2", hb: false },
  { key: "k_per_9", label: "K/9", get: (x) => x.box && x.box.k_per_9, t: "dec2", hb: true },
  { key: "bb_per_9", label: "BB/9", get: (x) => x.box && x.box.bb_per_9, t: "dec2", hb: false },
];

function renderProspects() {
  const P = (window.CS_DRAFT_PROSPECTS && window.CS_DRAFT_PROSPECTS.pitchers) || [];
  const years = [...new Set(P.map((x) => x.year).filter(Boolean))].sort((a, b) => b - a);
  const yf = state.prospectYear != null ? state.prospectYear : (years[0] || "all");
  const cols = PROSPECT_COLS_PIT;
  const sortKey = state.prospectSort || "fv";
  const col = cols.find((c) => c.key === sortKey) || cols[0];
  const dir = state.prospectDir != null ? state.prospectDir : (col.hb ? -1 : 1);
  const fmt = (t, v) => {
    if (v == null || Number.isNaN(v)) return " - ";
    if (t === "ceil") return Math.ceil(v);
    if (t === "dec1") return v.toFixed(1);
    if (t === "dec2") return v.toFixed(2);
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
    const b = x.box || {};
    const wl = (b.w != null || b.l != null) ? `${b.w == null ? 0 : b.w}-${b.l == null ? 0 : b.l}` : " - ";
    const nameCell = x.cs
      ? `<a class="proj-name" href="#/player/${x.cs.year}/${x.cs.slug}" title="Open CollegeSavant page">${escapeHtml(x.name || "")}</a>`
      : `<strong>${escapeHtml(x.name || "")}</strong>`;
    // School links to its PROSPX college page (entity router canonicalizes the
    // raw school string on its end, so no name mapping is needed here).
    const schoolHtml = x.school
      ? `<a class="cs-college-link" href="/prospx/#college=${encodeURIComponent(x.school)}" title="${escapeHtml(x.school)} on PROSPX">${escapeHtml(x.school)}</a>`
      : "";
    const cells = cols.map((c) => `<td class="tt-col${c.key === sortKey ? " is-sorted" : ""}">${fmt(c.t, c.get(x))}</td>`).join("");
    return `<tr><td class="tt-rank">${i + 1}</td>
      <td class="tt-team">${nameCell}<span class="tt-n">${schoolHtml}${x.pos ? " · " + escapeHtml(x.pos) : ""}</span></td>
      ${cells}<td class="tt-col">${wl}</td></tr>`;
  }).join("");
  app.innerHTML = `
    <section class="toolbar">
      <select class="select-box" data-prospect-year aria-label="Draft year">
        <option value="all" ${yf === "all" ? "selected" : ""}>All draft years</option>
        ${years.map((y) => `<option value="${y}" ${y === yf ? "selected" : ""}>${y} draft</option>`).join("")}
      </select>
    </section>
    <div class="panel-title"><span>Draft Prospects in college</span><span>${list.length} pitching prospect${list.length === 1 ? "" : "s"} · conventional college stats, click a column to sort</span></div>
    <p class="trans-note">Draft-eligible pitchers carried into CollegeSavant by the college box scores we hold (FanGraphs / NCAA), including prospects with no tracking. FV is the consensus board grade, rounded up. Names link to a player's CollegeSavant page when they have tracking data. This board is box-score based; the tracked CS+ and pitch-shape views cover only players with tracking data.</p>
    <section class="leaderboard tt-board"><div class="tt-scroll"><table class="tt-table">
      <thead><tr><th class="tt-rank">#</th><th class="tt-team">Prospect</th>${head}<th class="tt-col">W-L</th></tr></thead>
      <tbody>${body || `<tr><td colspan="${cols.length + 3}" class="note-line">No draft prospects with college stats for this year.</td></tr>`}</tbody>
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

// ---- Trust copy, read off the backtest ---------------------------------------
// Which leg of the college -> Single-A translation to trust is never written by
// hand. On the pitcher side it flipped as the matched sample grew (K% fell under
// the low-signal line and BB% rose above it), and a fixed sentence kept telling
// readers the opposite of the table under it. A leg whose r2 is below the
// payload's low-signal line is flagged: the same rule college_translation.py
// applies to the per-player low_confidence flags and the PROSPX chips.
function lowSignalR2() {
  const t = window.CS_TRANSLATION && window.CS_TRANSLATION.low_signal_r2;
  return typeof t === "number" ? t : 0.10;
}

function isLowSignal(f) {
  return !f || f.r2 == null || f.r2 < lowSignalR2();
}

function joinWords(xs) {
  return xs.length < 3 ? xs.join(" and ") : xs.slice(0, -1).join(", ") + ", and " + xs[xs.length - 1];
}

function upperFirst(s) {
  return s ? s.charAt(0).toUpperCase() + s.slice(1) : s;
}

// legs: [[eval key, reader-facing name]]. opts.brief drops the numbers (the
// player-page note); opts.unflagged says the surface prints no flag chip.
function trustSentence(E, legs, opts) {
  const o = opts || {};
  const have = legs.filter(([k]) => E[k] && E[k].r2 != null);
  if (!have.length) return "No backtest is on file, so no projection is marked as trusted.";
  const bar = `r² ${lowSignalR2().toFixed(2)}`;
  const detail = ([k, name]) => {
    if (o.brief) return name;
    const f = E[k];
    let s = `${name} (r² ${f.r2.toFixed(2)}`;
    if (f.mae != null && f.null_mae != null) {
      s += `, leave-one-out MAE ${f.mae.toFixed(3)} against ${f.null_mae.toFixed(3)} for predicting the Single-A mean`;
      // Under two standard errors of the paired gain, the leg has no
      // measurable edge over that mean, whichever way the point estimate leans.
      if (f.skill_se != null && Math.abs(f.null_mae - f.mae) < 2 * f.skill_se) s += ", no measurable edge over it";
    }
    return s + ")";
  };
  const strong = have.filter(([k]) => !isLowSignal(E[k]));
  const weak = have.filter(([k]) => isLowSignal(E[k]));
  const out = [];
  if (strong.length) {
    out.push(`${upperFirst(joinWords(strong.map(detail)))} ${strong.length > 1 ? "clear" : "clears"} the ${bar} bar in the current backtest.`);
  }
  if (weak.length) {
    const one = weak.length === 1;
    const where = strong.length ? "that bar" : `the ${bar} bar`;
    const flag = o.unflagged ? "" : ` and ${one ? "is" : "are"} flagged`;
    out.push(`${upperFirst(joinWords(weak.map(detail)))} ${one ? "falls" : "fall"} below ${where}${flag}; read ${one ? "it" : "them"} as context, not a forecast.`);
  }
  return out.join(" ");
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
      const flag = (f.r2 != null && f.r2 < lowSignalR2()) ? ` <span class="trans-flag">low signal</span>` : "";
      return `<tr><td class="tt-team">${label}${flag}</td>
        <td class="tt-col">${f.r2 != null ? f.r2.toFixed(2) : " - "}</td>
        <td class="tt-col">${f.band_sd != null ? `±${f.band_sd}` : " - "}</td>
        <td class="tt-col">${f.mae ?? " - "}</td>
        <td class="tt-col">${cov}</td><td class="tt-col">${f.n ?? " - "}</td></tr>`;
    }).join("");
  const pband = (b) => b == null ? " - " : b.exp.toFixed(1) + "%";
  // A leg below the low-signal line (the table's own flag) carries the flag in
  // the board header and its cells are muted (census M03-05).
  const legFlag = (k) => (E[k] && E[k].r2 != null && E[k].r2 < lowSignalR2()) ? "low signal" : "";
  const legHead = (label, flag) => flag ? `${label} <span class="trans-flag">${flag}</span>` : label;
  const MUTED = ' style="opacity:0.55"';
  const fk = legFlag("pit_k"), fb = legFlag("pit_bb");
  const list = state.pitchers
    .map((p) => ({ p, t: T[p.slug], cs: state.csPlus && state.csPlus.get(p.slug) }))
    .filter((x) => x.t && x.t.single_a)
    .sort((a, b) => (b.cs ?? -Infinity) - (a.cs ?? -Infinity))
    .slice(0, LEADERBOARD_LIMIT);
  const body = list.map((x, i) => {
    const sa = x.t.single_a;
    const logo = x.p.team && TEAM_LOGOS.has(x.p.team) ? `<img class="tt-logo" src="logos/${escapeHtml(x.p.team)}.png" alt="" loading="lazy" onerror="this.remove()">` : "";
    return `<tr><td class="tt-rank">${i + 1}</td>
      <td class="tt-team">${logo}<a class="proj-name" href="#/player/${x.p.year}/${x.p.slug}">${escapeHtml(displayName(x.p.pitcher_name))}</a></td>
      <td class="tt-col">${plusPill(x.cs, "CS+")}</td>
      <td class="tt-col"${fk ? MUTED : ""}>${pband(sa.k_pct)}</td>
      <td class="tt-col"${fb ? MUTED : ""}>${pband(sa.bb_pct)}</td></tr>`;
  }).join("");
  app.innerHTML = `
    <section class="toolbar">${renderYearSelect()}</section>
    <div class="panel-title"><span>How the projection works</span><span>college-to-Single-A statistical translation</span></div>
    <ol class="proj-method">
      <li><strong>Matched pairs.</strong> We take college pitchers who later reached Single-A, pair each one's college rate with the Single-A rate they actually posted, and fit how the two relate. Strikeout and walk rates are read from K/9 and BB/9 over batters faced.</li>
      <li><strong>Regression to the mean.</strong> A college rate is pulled toward the Single-A average by an amount set from how strongly the two levels track in the data, a fitted slope shrunk for sample size. An extreme college number is moderated, not copied straight across.</li>
      <li><strong>Bands.</strong> The P10-P90 band is the spread of the model's misses on arms it was not fit on (leave-one-out). Coverage near 80% in the table below means the band is sized to the data.</li>
      <li><strong>What to trust.</strong> ${trustSentence(E, [["pit_k", "strikeout rate"], ["pit_bb", "walk rate"]])}</li>
      <li><strong>What it does not do.</strong> No schedule-strength or park adjustment, since no college conference or park table is held. Stuff+, CS+, and the tracked pitch shapes describe college stuff; they are not a scouting Future Value, which the tracked data does not predict.</li>
    </ol>
    <div class="panel-title" style="margin-top:18px;"><span class="g-term" data-gl="single_a_equivalent">How accurate is this</span><span>leave-one-out backtest on the matched college-to-Single-A pairs</span></div>
    <section class="leaderboard tt-board"><div class="tt-scroll"><table class="tt-table">
      <thead><tr><th class="tt-team">Projection</th><th class="tt-col">r²</th><th class="tt-col">±band</th><th class="tt-col">MAE</th><th class="tt-col">P10-P90 cover</th><th class="tt-col">n pairs</th></tr></thead>
      <tbody>${accRows || `<tr><td colspan="6" class="note-line">No backtest on file.</td></tr>`}</tbody>
    </table></div></section>
    <div class="panel-title" style="margin-top:18px;"><span>Projected Single-A board</span><span>${list.length} pitchers with a projection · ranked by CS+ (pro profile)</span></div>
    <section class="leaderboard tt-board"><div class="tt-scroll"><table class="tt-table">
      <thead><tr><th class="tt-rank">#</th><th class="tt-team">Pitcher</th><th class="tt-col">CS+</th><th class="tt-col">${legHead("Proj A K%", fk)}</th><th class="tt-col">${legHead("Proj A BB%", fb)}</th></tr></thead>
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
    <p class="note-line">College pitching-staff tendencies for ${state.year}: every staff with at least ${TEAM_MIN_ARMS} tracked arms, aggregated across its pitchers. Team CS+ is the mean of its arms' CS+ (100 = the ${state.year} pool average, ${poolText(state.year)}).</p>
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
// shows projected Single-A K% / BB% (expected + P10-P90 band). Each row carries
// the low_confidence flag the translation set from the backtest, and the note
// names the trusted leg from the same eval; stuff/shapes are descriptive only
// (the CS+ index), never an outcome forecast. Empty when no translation.
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
      <span class="trans-band">${pct(b.lo)} - ${pct(b.hi)}</span>
    </div>`;
  };
  const rows = [
    row("Proj. Single-A K%", sa.k_pct, sa.k_pct && sa.k_pct.low_confidence ? "low confidence" : null),
    row("Proj. Single-A BB%", sa.bb_pct, sa.bb_pct && sa.bb_pct.low_confidence ? "low confidence" : null),
  ].join("");
  if (!rows.trim()) return "";
  const E = (window.CS_TRANSLATION && window.CS_TRANSLATION.eval) || {};
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
      <p class="trans-note">Matched-pair projection from this college K% / BB% to a Single-A
      expectation, fit on our own college-to-Single-A pairs. Not adjusted for schedule
      strength or park. The band is the P10-P90 range. ${trustSentence(E, [["pit_k", "strikeout rate"], ["pit_bb", "walk rate"]], { brief: true })}
      Stuff+ and pitch shapes stay descriptive (the CS+ index), not a pro outcome forecast.</p>
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
          <div data-export-chart data-export-title="Pitch shapes - Stuff+">${renderPitchShapePlot(pitcher)}</div>
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
    if (pitchDataLoading(pitcher.year)) {
      return `<div class="chart-empty">Loading ${pitcher.year} pitch data&hellip;</div>`;
    }
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
  // While a lazily fetched season's pitch table is still in flight the toggle
  // shows a loading state; the onload repaint clears it.
  const loading = pitchDataLoading(state.year);
  return `
    <select class="select-box year-select${loading ? " is-loading" : ""}" aria-label="Select season"${loading ? ` aria-busy="true" title="Loading ${state.year} pitch data"` : ""}>
      ${years.map((year) => `<option value="${year}" ${year === state.year ? "selected" : ""}>${year} · ${poolText(year)}</option>`).join("")}
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

// Boot LAST: init() renders the current hash synchronously, so on a cold
// deep link it reads top-level consts (leaderboard columns, team tendency
// metrics, prospect columns, loader state) that must already be initialized.
init();
