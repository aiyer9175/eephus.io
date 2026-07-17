const DRAFT_LENGTH = 400;
const POST_TENTH_ROUND_SLOT = 150000;
const officialSlotValues = {
  "1": 11350600,
  "2": 10507000,
  "3": 9740100,
  "4": 8988400,
  "5": 8336500,
  "6": 7746100,
  "7": 7327200,
  "8": 6982600,
  "9": 6675300,
  "10": 6393100,
  "11": 6133500,
  "12": 5889300,
  "13": 5661300,
  "14": 5444900,
  "15": 5241000,
  "16": 5051900,
  "17": 4868600,
  "18": 4695500,
  "19": 4530500,
  "20": 4373900,
  "21": 4224700,
  "22": 4082700,
  "23": 3947600,
  "24": 3818700,
  "25": 3696000,
  "26": 3578800,
  "27": 3466500,
  "28": 3363600,
  "29": 3270200,
  "30": 3190500,
  "31": 3118300,
  "32": 3044600,
  "33": 2970200,
  "34": 2897400,
  "35": 2826700,
  "36": 2758800,
  "37": 2696700,
  "38": 2633100,
  "39": 2571700,
  "40": 2504200,
  "41": 2446100,
  "42": 2388800,
  "43": 2333200,
  "44": 2278700,
  "45": 2225800,
  "46": 2181600,
  "47": 2131300,
  "48": 2081900,
  "49": 2033400,
  "50": 1982700,
  "51": 1938100,
  "52": 1892500,
  "53": 1848200,
  "54": 1805300,
  "55": 1763000,
  "56": 1721700,
  "57": 1677400,
  "58": 1637700,
  "59": 1598900,
  "60": 1561000,
  "61": 1523600,
  "62": 1487200,
  "63": 1451700,
  "64": 1416600,
  "65": 1382600,
  "66": 1353100,
  "67": 1317300,
  "68": 1285500,
  "69": 1254200,
  "70": 1223100,
  "71": 1192600,
  "72": 1174300,
  "73": 1156400,
  "74": 1138600,
  "75": 1120900,
  "76": 1103500,
  "77": 1086600,
  "78": 1069600,
  "79": 1052700,
  "80": 1035700,
  "81": 1018500,
  "82": 1003800,
  "83": 988700,
  "84": 973700,
  "85": 958500,
  "86": 943600,
  "87": 929700,
  "88": 915100,
  "89": 900800,
  "90": 887000,
  "91": 872900,
  "92": 859900,
  "93": 846900,
  "94": 833800,
  "95": 823800,
  "96": 815700,
  "97": 808100,
  "98": 800000,
  "99": 792300,
  "100": 784400,
  "101": 778200,
  "102": 770600,
  "103": 762900,
  "104": 755300,
  "105": 747700,
  "106": 740500,
  "107": 733100,
  "108": 725900,
  "109": 718700,
  "110": 711800,
  "111": 704900,
  "112": 697700,
  "113": 691000,
  "114": 684300,
  "115": 677500,
  "116": 670900,
  "117": 664500,
  "118": 658100,
  "119": 651500,
  "120": 645100,
  "121": 638800,
  "122": 632500,
  "123": 626500,
  "124": 620300,
  "125": 614500,
  "126": 609200,
  "127": 603500,
  "128": 597400,
  "129": 591700,
  "130": 585700,
  "131": 581100,
  "132": 575300,
  "133": 569600,
  "134": 563900,
  "135": 558400,
  "136": 553100,
  "137": 547700,
  "138": 542200,
  "139": 536900,
  "140": 532000,
  "141": 526600,
  "142": 521500,
  "143": 516300,
  "144": 511400,
  "145": 506100,
  "146": 501300,
  "147": 496400,
  "148": 491700,
  "149": 486800,
  "150": 481800,
  "151": 476900,
  "152": 472500,
  "153": 467700,
  "154": 463200,
  "155": 458500,
  "156": 454100,
  "157": 449500,
  "158": 445200,
  "159": 441300,
  "160": 437200,
  "161": 433200,
  "162": 429100,
  "163": 425400,
  "164": 421300,
  "165": 417400,
  "166": 413900,
  "167": 410300,
  "168": 406800,
  "169": 403500,
  "170": 399800,
  "171": 396300,
  "172": 393100,
  "173": 389900,
  "174": 386500,
  "175": 383400,
  "176": 380200,
  "177": 377000,
  "178": 373800,
  "179": 370600,
  "180": 367600,
  "181": 364600,
  "182": 361900,
  "183": 358900,
  "184": 355700,
  "185": 352900,
  "186": 350100,
  "187": 347300,
  "188": 344400,
  "189": 341800,
  "190": 338800,
  "191": 335900,
  "192": 333200,
  "193": 330300,
  "194": 327700,
  "195": 325100,
  "196": 322300,
  "197": 319600,
  "198": 317100,
  "199": 314300,
  "200": 311700,
  "201": 310000,
  "202": 307300,
  "203": 304800,
  "204": 302300,
  "205": 299700,
  "206": 297100,
  "207": 294800,
  "208": 292300,
  "209": 289900,
  "210": 287800,
  "211": 285400,
  "212": 283000,
  "213": 280900,
  "214": 278700,
  "215": 276400,
  "216": 274300,
  "217": 272000,
  "218": 270000,
  "219": 267800,
  "220": 266100,
  "221": 264100,
  "222": 262300,
  "223": 260300,
  "224": 258400,
  "225": 256500,
  "226": 254900,
  "227": 253300,
  "228": 251500,
  "229": 249300,
  "230": 247900,
  "231": 245800,
  "232": 244500,
  "233": 242700,
  "234": 241000,
  "235": 239200,
  "236": 237800,
  "237": 236100,
  "238": 234700,
  "239": 233400,
  "240": 232100,
  "241": 231000,
  "242": 229700,
  "243": 228600,
  "244": 227200,
  "245": 226300,
  "246": 225300,
  "247": 224100,
  "248": 223100,
  "249": 222200,
  "250": 220900,
  "251": 220400,
  "252": 219500,
  "253": 218500,
  "254": 217800,
  "255": 217000,
  "256": 216100,
  "257": 215400,
  "258": 214800,
  "259": 213900,
  "260": 213300,
  "261": 212600,
  "262": 212000,
  "263": 211200,
  "264": 210600,
  "265": 210200,
  "266": 209500,
  "267": 209000,
  "268": 208500,
  "269": 207900,
  "270": 207200,
  "271": 206800,
  "272": 206300,
  "273": 205800,
  "274": 205400,
  "275": 205000,
  "276": 204400,
  "277": 204100,
  "278": 203500,
  "279": 202900,
  "280": 202700,
  "281": 202500,
  "282": 202100,
  "283": 201700,
  "284": 201500,
  "285": 200900,
  "286": 200100,
  "287": 199900,
  "288": 199500,
  "289": 199200,
  "290": 198900,
  "291": 198600,
  "292": 198300,
  "293": 197900,
  "294": 197400,
  "295": 197200,
  "296": 196500,
  "297": 196200,
  "298": 196000,
  "299": 195600,
  "300": 195200,
  "301": 195000,
  "302": 194800,
  "303": 194500,
  "304": 194000,
  "305": 193700,
  "306": 193600,
  "307": 193300,
  "308": 193000,
  "309": 192500,
  "310": 192300,
  "311": 191900,
  "312": 191900,
  "313": 191900
};
const officialOpeningDraftOrder = [
  "CHW", "TB", "MIN", "SF", "PIT", "KC", "BAL", "OAK", "ATL", "COL",
  "WSH", "LAA", "STL", "MIA", "ARI", "TEX", "HOU", "CIN", "CLE", "BOS",
  "SD", "DET", "CHC", "SEA", "MIL", "ATL", "NYM", "HOU", "CLE", "KC",
  "ARI", "STL", "BAL", "PIT", "NYY", "PHI", "COL", "COL", "TOR", "LAD"
];
const roundDraftOrder = [
  "CHW", "TB", "MIN", "SF", "PIT", "KC", "BAL", "OAK", "ATL", "COL",
  "WSH", "LAA", "STL", "MIA", "ARI", "TEX", "HOU", "CIN", "CLE", "BOS",
  "SD", "DET", "CHC", "SEA", "MIL", "NYM", "NYY", "PHI", "TOR", "LAD"
];
const logoIds = {
  COL: 115,
  MIA: 146,
  LAA: 108,
  WSH: 120,
  CHW: 145,
  OAK: 133,
  PIT: 134,
  KC: 118,
  TOR: 141,
  STL: 138,
  SF: 137,
  CIN: 113,
  TB: 139,
  TEX: 140,
  SEA: 136,
  MIN: 142,
  CHC: 112,
  BOS: 111,
  ARI: 109,
  NYM: 121,
  DET: 116,
  SD: 135,
  BAL: 110,
  MIL: 158,
  ATL: 144,
  HOU: 117,
  NYY: 147,
  PHI: 143,
  LAD: 119,
  CLE: 114
};
const draftOrder = Array.from({ length: DRAFT_LENGTH }, (_, index) => {
  return officialOpeningDraftOrder[index] || roundDraftOrder[(index - officialOpeningDraftOrder.length) % roundDraftOrder.length];
});

const teams = [
  team("COL", "Colorado Rockies", "Rockies", "#7c3aed", ["SP", "SS", "OF"]),
  team("MIA", "Miami Marlins", "Marlins", "#06b6d4", ["SS", "C", "SP"]),
  team("LAA", "Los Angeles Angels", "Angels", "#ef4444", ["SP", "OF", "3B"]),
  team("WSH", "Washington Nationals", "Nationals", "#dc2626", ["OF", "SS", "SP"]),
  team("CHW", "Chicago White Sox", "White Sox", "#94a3b8", ["SS", "SP", "C"]),
  team("OAK", "Athletics", "Athletics", "#16a34a", ["OF", "1B", "SP"]),
  team("PIT", "Pittsburgh Pirates", "Pirates", "#f59e0b", ["C", "OF", "SP"]),
  team("KC", "Kansas City Royals", "Royals", "#38bdf8", ["SP", "3B", "OF"]),
  team("TOR", "Toronto Blue Jays", "Blue Jays", "#2563eb", ["SS", "OF", "C"]),
  team("STL", "St. Louis Cardinals", "Cardinals", "#e11d48", ["SP", "SS", "OF"]),
  team("SF", "San Francisco Giants", "Giants", "#f97316", ["OF", "SS", "SP"]),
  team("CIN", "Cincinnati Reds", "Reds", "#ef4444", ["SP", "C", "OF"]),
  team("TB", "Tampa Bay Rays", "Rays", "#0ea5e9", ["SS", "SP", "OF"]),
  team("TEX", "Texas Rangers", "Rangers", "#2563eb", ["SP", "OF", "3B"]),
  team("SEA", "Seattle Mariners", "Mariners", "#14b8a6", ["C", "SS", "OF"]),
  team("MIN", "Minnesota Twins", "Twins", "#1d4ed8", ["SP", "OF", "1B"]),
  team("CHC", "Chicago Cubs", "Cubs", "#2563eb", ["3B", "SP", "C"]),
  team("BOS", "Boston Red Sox", "Red Sox", "#dc2626", ["SP", "SS", "OF"]),
  team("ARI", "Arizona Diamondbacks", "D-backs", "#a21caf", ["OF", "SP", "C"]),
  team("NYM", "New York Mets", "Mets", "#f97316", ["SP", "OF", "SS"]),
  team("DET", "Detroit Tigers", "Tigers", "#0f172a", ["SS", "C", "SP"]),
  team("SD", "San Diego Padres", "Padres", "#a16207", ["OF", "SP", "1B"]),
  team("BAL", "Baltimore Orioles", "Orioles", "#f97316", ["SP", "C", "OF"]),
  team("MIL", "Milwaukee Brewers", "Brewers", "#facc15", ["SS", "SP", "OF"]),
  team("ATL", "Atlanta Braves", "Braves", "#b91c1c", ["SP", "OF", "C"]),
  team("HOU", "Houston Astros", "Astros", "#fb923c", ["1B", "SP", "OF"]),
  team("NYY", "New York Yankees", "Yankees", "#0f766e", ["3B", "SP", "OF"]),
  team("PHI", "Philadelphia Phillies", "Phillies", "#ef4444", ["OF", "SP", "SS"]),
  team("LAD", "Los Angeles Dodgers", "Dodgers", "#2563eb", ["SP", "C", "SS"]),
  team("CLE", "Cleveland Guardians", "Guardians", "#0ea5e9", ["OF", "SS", "SP"])
];

const players = (window.pgDraftPlayers || []).map(player => ({
  ...player,
  type: player.level === "C" ? "College" : "High School",
  levelLabel: player.level === "C" ? "College" : "High School",
  positions: normalizePositions(player.position),
  primaryPosition: normalizePositions(player.position)[0],
  positionRanks: {},
  tags: [player.school, player.hometown, player.state, player.commitment, player.position, player.level === "C" ? "college" : "high school"].filter(Boolean)
}));
assignPositionRanks(players);

const state = {
  pickIndex: 0,
  picks: [],
  started: false,
  completed: false,
  aiTimer: null,
  aiRunning: false,
  speed: 520,
  resultsView: "all",
  activeResultsTeam: "all",
  fullResultsTeam: "ALL",
  fullResultsRound: "ALL",
  demands: {},
  budgets: {},
  query: "",
  position: "ALL",
  type: "ALL",
  role: "ALL",
  teamMode: "single",
  primaryTeamId: "CHW",
  roundsToSim: "full",
  controlledTeamIds: new Set(["CHW"])
};

function sliderValueForSpeed(speed) {
  return Number(elements.speedSlider.max) + Number(elements.speedSlider.min) - speed;
}

function speedForSliderValue(value) {
  return Number(elements.speedSlider.max) + Number(elements.speedSlider.min) - Number(value);
}

function renderSpeedLabel() {
  elements.speedLabel.textContent = `${(state.speed / 1000).toFixed(2)}s per AI pick`;
}

const elements = {
  teamSelect: document.querySelector("#teamSelect"),
  teamMode: document.querySelector("#teamMode"),
  roundSelect: document.querySelector("#roundSelect"),
  controlledTeams: document.querySelector("#controlledTeams"),
  speedSlider: document.querySelector("#speedSlider"),
  speedLabel: document.querySelector("#speedLabel"),
  resultsView: document.querySelector("#resultsView"),
  resultsTabs: document.querySelector("#resultsTabs"),
  fullResultsTeam: document.querySelector("#fullResultsTeam"),
  fullResultsRound: document.querySelector("#fullResultsRound"),
  playerSearch: document.querySelector("#playerSearch"),
  positionFilter: document.querySelector("#positionFilter"),
  typeFilter: document.querySelector("#typeFilter"),
  roleFilter: document.querySelector("#roleFilter"),
  slateLabel: document.querySelector("#slateLabel"),
  draftTitle: document.querySelector("#draftTitle"),
  startDraft: document.querySelector("#startDraft"),
  autoPick: document.querySelector("#autoPick"),
  undoPick: document.querySelector("#undoPick"),
  resetDraft: document.querySelector("#resetDraft"),
  clockTeam: document.querySelector("#clockTeam"),
  clockPick: document.querySelector("#clockPick"),
  bestAvailable: document.querySelector("#bestAvailable"),
  bestAvailableMeta: document.querySelector("#bestAvailableMeta"),
  userGrade: document.querySelector("#userGrade"),
  userGradeMeta: document.querySelector("#userGradeMeta"),
  draftRecap: document.querySelector("#draftRecap"),
  draftRecapLogo: document.querySelector("#draftRecapLogo"),
  draftRecapGrade: document.querySelector("#draftRecapGrade"),
  draftRecapBody: document.querySelector("#draftRecapBody"),
  poolRoom: document.querySelector("#poolRoom"),
  poolRoomMeta: document.querySelector("#poolRoomMeta"),
  draftProgress: document.querySelector("#draftProgress"),
  draftProgressMeta: document.querySelector("#draftProgressMeta"),
  availableCount: document.querySelector("#availableCount"),
  playerBoard: document.querySelector("#playerBoard"),
  pickCard: document.querySelector("#pickCard"),
  controlledBadge: document.querySelector("#controlledBadge"),
  gradeLegend: document.querySelector("#gradeLegend"),
  resultsBody: document.querySelector("#resultsBody"),
  fullResultsBody: document.querySelector("#fullResultsBody"),
  draftContext: document.querySelector("#draftContext")
};

function team(id, name, shortName, color, needs) {
  return {
    id,
    name,
    shortName,
    color,
    needs,
    logo: `https://www.mlbstatic.com/team-logos/${logoIds[id]}.svg`
  };
}

function normalizePositions(position) {
  return position.split("/").map(item => {
    if (["RHP", "LHP"].includes(item)) return "SP";
    if (["MIF", "INF"].includes(item)) return "SS";
    if (["CIF"].includes(item)) return "3B";
    return item;
  });
}

function assignPositionRanks(pool) {
  const counts = {};
  pool
    .slice()
    .sort((a, b) => a.rank - b.rank)
    .forEach(player => {
      player.positions.forEach(position => {
        counts[position] = (counts[position] || 0) + 1;
        player.positionRanks[position] = counts[position];
      });
      player.positionRank = player.positionRanks[player.primaryPosition];
    });
}

function positionRankLabel(player, selectedPosition = "ALL") {
  if (!player) return "--";
  if (selectedPosition !== "ALL" && player.positionRanks[selectedPosition]) {
    return `${selectedPosition} #${player.positionRanks[selectedPosition]}`;
  }
  return player.positions
    .map(position => `${position} #${player.positionRanks[position]}`)
    .join(" / ");
}

function currentSlot() {
  const teamId = activeDraftOrder()[state.pickIndex];
  return teamId ? { pick: state.pickIndex + 1, team: teams.find(item => item.id === teamId) } : null;
}

function activeDraftLength() {
  if (state.roundsToSim === "full") return DRAFT_LENGTH;
  if (state.roundsToSim === 1) return officialOpeningDraftOrder.length;
  return Math.min(DRAFT_LENGTH, officialOpeningDraftOrder.length + (state.roundsToSim - 1) * roundDraftOrder.length);
}

function activeDraftOrder() {
  return draftOrder.slice(0, activeDraftLength());
}

function pickMeta(pick) {
  if (pick >= 26 && pick <= 34) {
    return { round: "CB-A", roundLabel: "Competitive Balance A", competitiveBalance: true };
  }
  if (pick <= 25) {
    return { round: "1", roundLabel: "Round 1", competitiveBalance: false };
  }
  if (pick <= 64) {
    return { round: "2", roundLabel: "Round 2", competitiveBalance: false };
  }
  const round = 3 + Math.floor((pick - 65) / roundDraftOrder.length);
  return { round: `${round}`, roundLabel: `Round ${round}`, competitiveBalance: false };
}

function teamLogo(team, className = "team-logo") {
  if (!team) return "";
  return `<img class="${className}" src="${team.logo}" alt="${team.name} logo" loading="lazy" onerror="this.replaceWith(Object.assign(document.createElement('span'), { className: '${className} logo-fallback', textContent: '${team.id}' }))" />`;
}

function draftedIds() {
  return new Set(state.picks.map(pick => pick.playerId));
}

function availablePlayers() {
  const selected = draftedIds();
  const query = state.query.trim().toLowerCase();
  return players
    .filter(player => !selected.has(player.id))
    .filter(player => state.position === "ALL" || player.positions.includes(state.position))
    .filter(player => state.type === "ALL" || player.type === state.type)
    .filter(player => state.role === "ALL" || (state.role === "P" ? isPitcher(player) : !isPitcher(player)))
    .filter(player => {
      const haystack = `${player.name} ${player.position} ${player.school} ${player.type} ${player.tags.join(" ")}`.toLowerCase();
      return haystack.includes(query);
    })
    .sort((a, b) => a.rank - b.rank);
}

function isPitcher(player) {
  return player.positions.includes("SP") || player.position.includes("RHP") || player.position.includes("LHP");
}

function bestAvailable() {
  return availablePlayers()[0] || players.filter(player => !draftedIds().has(player.id)).sort((a, b) => a.rank - b.rank)[0];
}

function controlledTeams() {
  if (state.teamMode === "all") return new Set(teams.map(item => item.id));
  if (state.teamMode === "single") return new Set([state.primaryTeamId]);
  return new Set(state.controlledTeamIds);
}

function isUserControlled(teamId) {
  return controlledTeams().has(teamId);
}

function slotValueForPick(pick) {
  return officialSlotValues[pick] || POST_TENTH_ROUND_SLOT;
}

function roundedBonus(value) {
  return Math.max(5000, Math.round(value / 100) * 100);
}

function baseDemandForPlayer(player) {
  const rankSlot = slotValueForPick(Math.min(player.rank, DRAFT_LENGTH));
  const isHighSchool = player.type === "High School";
  if (player.rank > 313) return isHighSchool ? 275000 : 35000;
  if (player.rank > 250) return roundedBonus(isHighSchool ? rankSlot * 1.22 : rankSlot * 0.22);
  if (player.rank > 150) return roundedBonus(isHighSchool ? rankSlot * 1.12 : rankSlot * 0.48);
  if (player.rank > 100) return roundedBonus(isHighSchool ? rankSlot * 1.06 : rankSlot * 0.68);
  if (player.rank > 50) return roundedBonus(isHighSchool ? rankSlot * 1.02 : rankSlot * 0.82);
  if (player.rank > 20) return roundedBonus(isHighSchool ? rankSlot * 1.00 : rankSlot * 0.88);
  if (player.rank > 10) return roundedBonus(isHighSchool ? rankSlot * 0.98 : rankSlot * 0.86);
  return roundedBonus(isHighSchool ? rankSlot * 1.02 : rankSlot * 0.82);
}

function demandKey(teamId, playerId) {
  return `${teamId}:${playerId}`;
}

function demandForPlayer(teamId, player) {
  const multiplier = state.demands[demandKey(teamId, player.id)] || 1;
  return roundedBonus(baseDemandForPlayer(player) * multiplier);
}

function teamPickSlots(teamId) {
  return draftOrder
    .map((pickTeamId, index) => ({ teamId: pickTeamId, pick: index + 1, slot: officialSlotValues[index + 1] || 0 }))
    .filter(item => item.teamId === teamId);
}

function createBudgets() {
  return teams.reduce((budgets, item) => {
    const slots = teamPickSlots(item.id);
    budgets[item.id] = {
      total: slots.reduce((sum, slot) => sum + slot.slot, 0),
      spent: 0,
      picks: slots.length
    };
    return budgets;
  }, {});
}

function createDemands() {
  return teams.reduce((demands, teamItem) => {
    players.forEach(player => {
      demands[demandKey(teamItem.id, player.id)] = demandMultiplierForPlayer(player);
    });
    return demands;
  }, {});
}

function demandMultiplierForPlayer(player) {
  const highSchool = player.type === "High School";
  if (highSchool && player.rank > 313) return randomBetween(0.85, 1.95);
  if (highSchool && player.rank > 150) return randomBetween(0.88, 1.48);
  if (highSchool) return randomBetween(0.88, 1.16);
  if (player.rank > 313) return Math.random() < 0.18 ? randomBetween(1.5, 4.25) : randomBetween(0.12, 0.95);
  if (player.rank > 250) return Math.random() < 0.16 ? randomBetween(1.2, 3.4) : randomBetween(0.18, 1.05);
  if (player.rank > 150) return Math.random() < 0.12 ? randomBetween(1.05, 1.9) : randomBetween(0.28, 1.05);
  if (player.rank > 50) return randomBetween(0.72, 1.08);
  return randomBetween(0.84, 1.08);
}

function randomBetween(low, high) {
  return low + Math.random() * (high - low);
}

function budgetForTeam(teamId) {
  return state.budgets[teamId] || { total: 0, spent: 0, picks: 0 };
}

function remainingBudget(teamId) {
  const budget = budgetForTeam(teamId);
  return budget.total - budget.spent;
}

function poolChargeForPick(pick, bonus) {
  if (pick > 313) return Math.max(0, bonus - POST_TENTH_ROUND_SLOT);
  return bonus;
}

function isOverBudget(teamId) {
  const budget = budgetForTeam(teamId);
  return budget.spent > budget.total;
}

function controlledBudgetFailed() {
  return Array.from(controlledTeams()).some(teamId => isOverBudget(teamId));
}

function futureControlledPickCount(teamId) {
  return activeDraftOrder().slice(state.pickIndex + 1).filter(pickTeamId => pickTeamId === teamId).length;
}

function futurePickCount(teamId) {
  return activeDraftOrder().slice(state.pickIndex + 1).filter(pickTeamId => pickTeamId === teamId).length;
}

function controlledBudgetSummary() {
  const teamIds = Array.from(controlledTeams());
  const total = teamIds.reduce((sum, teamId) => sum + budgetForTeam(teamId).total, 0);
  const spent = teamIds.reduce((sum, teamId) => sum + budgetForTeam(teamId).spent, 0);
  return { total, spent, remaining: total - spent };
}

function poolRoomLabel() {
  const teamIds = Array.from(controlledTeams());
  if (teamIds.length === 1) {
    const teamId = teamIds[0];
    const budget = budgetForTeam(teamId);
    return `${teamId}: ${formatMoneyShort(budget.spent)} spent of ${formatMoneyShort(budget.total)}`;
  }
  return teamIds
    .map(teamId => `${teamId} ${formatMoneyShort(remainingBudget(teamId))}`)
    .join(" | ");
}

function clearAiTimer() {
  if (state.aiTimer) {
    window.clearTimeout(state.aiTimer);
    state.aiTimer = null;
  }
  state.aiRunning = false;
}

function isDraftComplete() {
  return state.completed || state.pickIndex >= activeDraftLength() || state.picks.length >= players.length;
}

function currentPickIsUserControlled() {
  const slot = currentSlot();
  return Boolean(slot && isUserControlled(slot.team.id));
}

function startDraft({ preserveEconomics = false } = {}) {
  if (state.started) return;
  clearAiTimer();
  state.pickIndex = 0;
  state.picks = [];
  state.started = true;
  state.completed = false;
  state.activeResultsTeam = "all";
  if (!preserveEconomics || !Object.keys(state.demands).length) state.demands = createDemands();
  if (!preserveEconomics || !Object.keys(state.budgets).length) state.budgets = createBudgets();
  render();
  runAiPicksAnimated();
}

function handleStartInput(event) {
  event?.stopPropagation();
  startDraft();
}

function runAiPicksAnimated() {
  clearAiTimer();
  if (!state.started || isDraftComplete()) {
    state.completed = isDraftComplete();
    render();
    return;
  }
  const slot = currentSlot();
  if (!slot || isUserControlled(slot.team.id)) {
    render();
    return;
  }

  state.aiRunning = true;
  state.aiTimer = window.setTimeout(() => {
    state.aiTimer = null;
    const activeSlot = currentSlot();
    if (!activeSlot || isUserControlled(activeSlot.team.id) || isDraftComplete()) {
      state.aiRunning = false;
      render();
      return;
    }
    const playerId = selectAiPlayer(activeSlot.team, true);
    if (playerId) makePick(playerId, "ai");
    if (state.pickIndex >= activeDraftLength() || state.picks.length >= players.length) {
      state.completed = true;
      state.aiRunning = false;
      render();
      return;
    }
    render();
    runAiPicksAnimated();
  }, state.speed);
}

function markCompleteIfFinished() {
  if (state.pickIndex >= activeDraftLength() || state.picks.length >= players.length) {
    state.completed = true;
  }
}

function pickPlayer(playerId, source = "user") {
  if (!state.started) startDraft({ preserveEconomics: true });
  if (isDraftComplete()) return;
  const slot = currentSlot();
  if (!slot || draftedIds().has(playerId)) return;
  if (source === "user" && !isUserControlled(slot.team.id)) return;
  const player = players.find(item => item.id === playerId);
  if (source === "user" && player && demandForPlayer(slot.team.id, player) > remainingBudget(slot.team.id)) return;
  makePick(playerId, source);
  markCompleteIfFinished();
  render();
  runAiPicksAnimated();
}

function handlePlayerInput(playerId, event) {
  event?.stopPropagation();
  pickPlayer(playerId, "user");
}

function clearActionHash() {
  if (!window.location.hash) return;
  history.replaceState(null, "", window.location.pathname + window.location.search);
}

function handleActionHash() {
  const hash = window.location.hash;
  if (!hash) return;
  if (hash === "#start-draft") {
    startDraft();
    clearActionHash();
    return;
  }
  if (hash.startsWith("#pick-")) {
    pickPlayer(decodeURIComponent(hash.replace("#pick-", "")), "user");
    clearActionHash();
  }
}

function handleDraftAction(event) {
  const startButton = event.target.closest?.("#startDraft");
  if (startButton) {
    handleStartInput(event);
    return;
  }

  const playerButton = event.target.closest?.("[data-player-id]");
  if (playerButton && !playerButton.disabled && !playerButton.classList.contains("disabled")) {
    handlePlayerInput(playerButton.dataset.playerId, event);
  }
}

function makePick(playerId, source) {
  const slot = currentSlot();
  const player = players.find(item => item.id === playerId);
  if (!slot || !player) return;
  const bonus = demandForPlayer(slot.team.id, player);
  const poolCharge = poolChargeForPick(slot.pick, bonus);
  const meta = pickMeta(slot.pick);

  state.picks.push({
    pick: slot.pick,
    round: meta.round,
    roundLabel: meta.roundLabel,
    competitiveBalance: meta.competitiveBalance,
    teamId: slot.team.id,
    playerId,
    source,
    grade: gradePick(slot.pick, player.rank, bonus, slotValueForPick(slot.pick)),
    fit: fitLabel(slot.team, player),
    slotValue: slotValueForPick(slot.pick),
    bonus,
    poolCharge
  });
  if (state.budgets[slot.team.id]) {
    state.budgets[slot.team.id].spent += poolCharge;
  }
  state.pickIndex += 1;
}

function autoPick() {
  const slot = currentSlot();
  if (!state.started || !slot || !isUserControlled(slot.team.id) || isDraftComplete()) return;
  pickPlayer(selectAiPlayer(slot.team, true), "user");
}

function selectAiPlayer(team, enforceBudget = false) {
  const pool = players.filter(player => !draftedIds().has(player.id)).sort((a, b) => a.rank - b.rank);
  const futureReserve = futurePickCount(team.id) * 100000;
  const maxSpend = Math.max(10000, remainingBudget(team.id) - futureReserve);
  if (!enforceBudget) {
    const bestFit = pool.find(player => player.positions.some(position => team.needs.includes(position)));
    return (bestFit || pool[0])?.id;
  }
  const affordable = pool.filter(player => demandForPlayer(team.id, player) <= maxSpend);
  const fallbackAffordable = pool
    .filter(player => demandForPlayer(team.id, player) <= remainingBudget(team.id))
    .sort((a, b) => demandForPlayer(team.id, a) - demandForPlayer(team.id, b));
  const candidates = affordable.length ? affordable : fallbackAffordable;
  if (!candidates.length) return pool[0]?.id;
  const bestFit = candidates.find(player => player.positions.some(position => team.needs.includes(position)));
  return (bestFit || candidates[0])?.id;
}

function undoPick() {
  clearAiTimer();
  if (!state.picks.length) return;
  const removed = state.picks.pop();
  if (removed && state.budgets[removed.teamId]) {
    state.budgets[removed.teamId].spent = Math.max(0, state.budgets[removed.teamId].spent - removed.poolCharge);
  }
  state.pickIndex = Math.max(0, state.pickIndex - 1);
  state.completed = false;
  render();
}

function resetDraft() {
  clearAiTimer();
  state.pickIndex = 0;
  state.picks = [];
  state.started = false;
  state.completed = false;
  state.demands = createDemands();
  state.budgets = createBudgets();
  render();
}

function gradePick(pick, rank, bonus, slotValue) {
  const delta = pick - rank;
  const slot = Math.max(slotValue || 1, 1);
  const savingsRate = (slot - bonus) / slot;
  let score = 3.35;

  if (delta > 0) score += Math.min(0.85, delta * 0.04);
  if (delta < 0) {
    const reach = Math.abs(delta);
    score -= Math.min(3.2, 0.32 + reach * 0.24);
  }
  if (rank === 1 && pick === 1) score += 0.25;

  if (savingsRate > 0) score += Math.min(0.5, savingsRate * 1.15);
  else score += Math.max(-1.2, savingsRate * 2.25);

  if (score >= 3.65) return { letter: "A", tone: "positive", delta };
  if (score >= 2.9) return { letter: "B", tone: "", delta };
  if (score >= 2.05) return { letter: "C", tone: "warning", delta };
  if (score >= 1.1) return { letter: "D", tone: "negative", delta };
  return { letter: "F", tone: "grade-f", delta };
}

function fitLabel(team, player) {
  const matchedNeed = player.positions.find(position => team.needs.includes(position));
  return matchedNeed ? `${matchedNeed} need` : "Value board";
}

function render() {
  [
    renderControls,
    renderSummary,
    renderDraftRecap,
    renderPlayerBoard,
    renderPickCard,
    renderResults,
    renderFullResults,
    renderContext
  ].forEach(renderStep => {
    try {
      renderStep();
    } catch (error) {
      console.error(`Render failed in ${renderStep.name}`, error);
    }
  });
}

function renderControls() {
  elements.teamSelect.innerHTML = teams.map(item => `
    <option value="${item.id}" ${item.id === state.primaryTeamId ? "selected" : ""}>${item.name}</option>
  `).join("");
  elements.teamSelect.disabled = state.started;
  elements.teamMode.disabled = state.started;
  elements.roundSelect.disabled = state.started;
  elements.roundSelect.value = String(state.roundsToSim);
  elements.speedSlider.value = sliderValueForSpeed(state.speed);
  renderSpeedLabel();
  elements.resultsView.value = state.resultsView;
  elements.fullResultsTeam.innerHTML = [
    `<option value="ALL" ${state.fullResultsTeam === "ALL" ? "selected" : ""}>All teams</option>`,
    ...teams.map(item => `<option value="${item.id}" ${state.fullResultsTeam === item.id ? "selected" : ""}>${item.name}</option>`)
  ].join("");
  const draftedRounds = Array.from(new Set(state.picks.map(pick => pick.round || pickMeta(pick.pick).round)));
  elements.fullResultsRound.innerHTML = [
    `<option value="ALL" ${state.fullResultsRound === "ALL" ? "selected" : ""}>All rounds</option>`,
    ...draftedRounds.map(round => `<option value="${round}" ${state.fullResultsRound === round ? "selected" : ""}>${round === "CB-A" ? "Competitive Balance A" : `Round ${round}`}</option>`)
  ].join("");
  elements.fullResultsRound.value = draftedRounds.includes(state.fullResultsRound) ? state.fullResultsRound : "ALL";
  if (!draftedRounds.includes(state.fullResultsRound)) state.fullResultsRound = "ALL";
  elements.fullResultsTeam.disabled = state.fullResultsRound !== "ALL";

  const positions = ["ALL", ...Array.from(new Set(players.flatMap(player => player.positions))).sort()];
  elements.positionFilter.innerHTML = positions.map(position => `
    <option value="${position}" ${position === state.position ? "selected" : ""}>${position === "ALL" ? "All positions" : position}</option>
  `).join("");

  const types = ["ALL", ...Array.from(new Set(players.map(player => player.type))).sort()];
  elements.typeFilter.innerHTML = types.map(type => `
    <option value="${type}" ${type === state.type ? "selected" : ""}>${type === "ALL" ? "All player types" : type}</option>
  `).join("");
  elements.roleFilter.value = state.role;

  elements.controlledTeams.hidden = state.teamMode !== "multi";
  elements.controlledTeams.innerHTML = teams.map(item => `
    <label class="team-pill" style="--team-color: ${item.color}">
      <input type="checkbox" value="${item.id}" ${controlledTeams().has(item.id) ? "checked" : ""} ${state.started || state.teamMode !== "multi" ? "disabled" : ""} />
      <span>${item.id}</span>
    </label>
  `).join("");
}

function renderSummary() {
  const slot = currentSlot();
  const best = bestAvailable();
  const userPicks = state.picks.filter(pick => pick.source === "user");
  const userScore = userPicks.reduce((sum, pick) => sum + gradePoints(pick.grade.letter), 0);
  const avg = userPicks.length ? userScore / userPicks.length : null;
  const complete = isDraftComplete();
  const budgetFailed = controlledBudgetFailed();
  const meta = slot ? pickMeta(slot.pick) : null;

  elements.slateLabel.textContent = "2026 MLB Draft Order";
  elements.draftTitle.textContent = !state.started ? "Choose your team and start the draft" : complete ? "Draft complete" : `${slot.team.shortName} on the clock`;
  elements.clockTeam.innerHTML = !state.started ? "Ready" : complete ? "Done" : `<span class="score-team">${teamLogo(slot.team, "team-logo score-logo")}<span>${slot.team.id}</span></span>`;
  elements.clockPick.textContent = !state.started ? "Pick 1 waiting" : complete ? `${state.picks.length} picks made` : `${meta.roundLabel} · Pick ${slot.pick}${meta.competitiveBalance ? " · Competitive Balance" : ""}`;
  elements.bestAvailable.textContent = best ? best.name : "None";
  elements.bestAvailable.style.setProperty("--name-length", String(best ? best.name.length : 4));
  fitBestAvailableName();
  elements.bestAvailableMeta.textContent = best ? `No. ${best.rank} PG rank · ${positionRankLabel(best, state.position)} · ${best.school}` : "Board empty";
  const summaryGrade = budgetFailed ? "F" : avg ? letterFromPoints(avg) : "--";
  elements.userGrade.textContent = summaryGrade;
  elements.userGrade.className = gradeClass(summaryGrade);
  elements.userGradeMeta.textContent = !state.started ? "Start the draft" : budgetFailed ? "Controlled pool exceeded" : userPicks.length ? `${userPicks.length} controlled picks ${complete ? "final" : "so far"}` : "AI is drafting until your first pick";
  const budgetSummary = controlledBudgetSummary();
  elements.poolRoom.textContent = state.started ? formatMoneyShort(budgetSummary.remaining) : "--";
  elements.poolRoomMeta.textContent = state.started ? poolRoomLabel() : "Locks at start";
  const draftLength = activeDraftLength();
  elements.draftProgress.textContent = `${state.picks.length}/${draftLength}`;
  elements.draftProgressMeta.textContent = `${draftLength - state.picks.length} picks remaining`;
  elements.startDraft.classList.toggle("disabled", state.started);
  elements.startDraft.setAttribute("aria-disabled", state.started ? "true" : "false");
  elements.autoPick.disabled = state.aiRunning || !state.started || complete || !currentPickIsUserControlled();
  elements.undoPick.disabled = state.aiRunning || !state.picks.length;
  document.documentElement.style.setProperty("--active-team", slot?.team.color || "#16a34a");
}

function fitBestAvailableName() {
  const element = elements.bestAvailable;
  element.style.fontSize = "";
  requestAnimationFrame(() => {
    const availableWidth = element.parentElement.clientWidth - 34;
    if (!availableWidth) return;
    let size = 42;
    element.style.fontSize = `${size}px`;
    while (element.scrollWidth > availableWidth && size > 16) {
      size -= 1;
      element.style.fontSize = `${size}px`;
    }
  });
}

function controlledPickGrade() {
  const userPicks = state.picks.filter(pick => pick.source === "user");
  if (controlledBudgetFailed()) return "F";
  if (!userPicks.length) return "--";
  const average = userPicks.reduce((sum, pick) => sum + gradePoints(pick.grade.letter), 0) / userPicks.length;
  return letterFromPoints(average);
}

function renderDraftRecap() {
  const complete = isDraftComplete();
  const userPicks = state.picks.filter(pick => pick.source === "user");
  elements.draftRecap.hidden = !complete || !userPicks.length;
  if (elements.draftRecap.hidden) return;

  const controlledIds = Array.from(new Set(userPicks.map(pick => pick.teamId)));
  const primaryTeam = teams.find(item => item.id === (controlledIds[0] || state.primaryTeamId));
  const grade = controlledPickGrade();
  elements.draftRecapLogo.innerHTML = controlledIds.length === 1
    ? teamLogo(primaryTeam, "team-logo recap-team-logo")
    : `<span class="recap-multi-logo">${controlledIds.length}</span>`;
  elements.draftRecapGrade.textContent = grade;
  elements.draftRecapGrade.className = gradeClass(grade);
  elements.draftRecapBody.innerHTML = controlledIds.map(teamId => renderTeamRecap(teamId, userPicks)).join("");
}

function renderTeamRecap(teamId, userPicks) {
  const team = teams.find(item => item.id === teamId);
  const picks = userPicks.filter(pick => pick.teamId === teamId);
  const budget = budgetForTeam(teamId);
  const percentSpent = budget.total ? Math.round((budget.spent / budget.total) * 100) : 0;
  return `
    <article class="recap-team" style="--team-color: ${team?.color || "#f59e0b"}">
      <div class="recap-team-heading">
        <div>
          <span>${team?.name || teamId}</span>
          <strong>${picks.length} pick${picks.length === 1 ? "" : "s"}</strong>
          <div class="recap-budget-line">
            Pool ${formatMoneyShort(budget.total)} · Spent ${formatMoneyShort(budget.spent)} (${percentSpent}%) · Left ${formatMoneyShort(budget.total - budget.spent)}
          </div>
        </div>
        ${teamLogo(team, "team-logo recap-small-logo")}
      </div>
      <div class="recap-pick-list">
        ${picks.map(renderRecapPick).join("")}
      </div>
    </article>
  `;
}

function renderRecapPick(pick) {
  const player = players.find(item => item.id === pick.playerId);
  const meta = pick.round ? pick : pickMeta(pick.pick);
  const grade = pick.grade?.letter || "--";
  const slotDelta = (pick.slotValue || 0) - (pick.bonus || 0);
  return `
    <div class="recap-pick-row">
      <div class="recap-pick-meta">
        <span>${meta.round === "CB-A" ? "CB-A" : `R${meta.round}`}: ${pick.pick}</span>
        <strong>${player?.position || "--"}</strong>
      </div>
      <div class="recap-player">
        <strong>${cleanPlayerName(player?.name || "Unknown player")}</strong>
        <span>${player?.school || "--"} · ${player?.type || "--"} · PG #${player?.rank || "--"} · ${positionRankLabel(player)}</span>
      </div>
      <div class="recap-money">
        <span>Bonus</span>
        <strong>${formatMoneyShort(pick.bonus || 0)}</strong>
        <small class="${slotDelta >= 0 ? "positive" : "negative"}">${formatSlotSavings(slotDelta)}</small>
      </div>
      <div class="recap-grade-mark ${gradeClass(grade) || pick.grade?.tone || ""}">
        ${grade}
      </div>
    </div>
  `;
}

function cleanPlayerName(name) {
  return name.replace(/\*+$/g, "").trim();
}

function renderPlayerBoard() {
  const slot = currentSlot();
  const controlled = !isDraftComplete() && slot && isUserControlled(slot.team.id);
  const options = availablePlayers();
  elements.availableCount.textContent = `${options.length} left`;
  if (isDraftComplete()) {
    elements.availableCount.textContent = "Done";
    elements.playerBoard.innerHTML = `<div class="empty-list">Draft complete. Review every pick grade in the results table.</div>`;
    return;
  }
  elements.playerBoard.innerHTML = options.length ? options.map(player => {
    const ask = controlled ? demandForPlayer(slot.team.id, player) : baseDemandForPlayer(player);
    const slotValue = slot ? slotValueForPick(slot.pick) : 0;
    const affordable = !controlled || ask <= remainingBudget(slot.team.id);
    return `
    <article class="player-card ${affordable ? "" : "unaffordable"}">
      <div class="rank-block">
        <strong>${player.rank}</strong>
        <span>rank</span>
      </div>
      <div class="player-main">
        <div class="player-header">
          <div>
            <strong>${player.name}</strong>
          <span>${player.position} · ${player.school} · ${player.type} · ${positionRankLabel(player, state.position)}</span>
          </div>
          <span class="type-badge">${player.batsThrows}</span>
        </div>
        <p>${player.hometown}, ${player.state}${player.commitment ? ` · Commitment: ${player.commitment}` : ""}</p>
        <div class="tool-row">
          <span>Ask ${formatMoneyShort(ask)}</span>
          <span>${formatSlotSavings(slotValue - ask)}</span>
          <span>${player.levelLabel}</span>
        </div>
      </div>
      <a class="${!controlled || !affordable ? "disabled" : ""}" href="${controlled && affordable ? `#pick-${encodeURIComponent(player.id)}` : "#"}" data-player-id="${player.id}" onpointerdown="window.DraftApp?.pick(this.dataset.playerId, event)" onclick="window.DraftApp?.pick(this.dataset.playerId, event)">${affordable ? "Draft" : "Over Budget"}</a>
    </article>
  `;
  }).join("") : `<div class="empty-list">No available players match these filters.</div>`;
  wirePlayerButtons();
}

function wirePlayerButtons() {
  elements.playerBoard.querySelectorAll("[data-player-id]").forEach(button => {
    if (button.classList.contains("disabled")) return;
    button.onpointerdown = event => handlePlayerInput(button.dataset.playerId, event);
    button.onmousedown = event => handlePlayerInput(button.dataset.playerId, event);
    button.ontouchstart = event => handlePlayerInput(button.dataset.playerId, event);
    button.onclick = event => handlePlayerInput(button.dataset.playerId, event);
  });
}

function renderPickCard() {
  const slot = currentSlot();
  if (!state.started) {
    elements.controlledBadge.textContent = "Setup";
    elements.pickCard.innerHTML = `
      <div class="empty-list">Select one team, multiple teams, or all teams, then start the draft. The AI will automatically make every non-controlled selection.</div>
    `;
    return;
  }

  if (isDraftComplete() || !slot) {
    elements.controlledBadge.textContent = "Done";
    elements.pickCard.innerHTML = `
      <div class="empty-list">All ${state.picks.length} picks are complete. The overall grade reflects your controlled-team selections.</div>
    `;
    return;
  }

  const controlled = isUserControlled(slot.team.id);
  const best = bestAvailable();
  const currentSlotValue = slotValueForPick(slot.pick);
  const bestAsk = best ? demandForPlayer(slot.team.id, best) : 0;
  const remaining = remainingBudget(slot.team.id);
  const meta = pickMeta(slot.pick);
  const postTenthReminder = Number(meta.round) > 10 ? `
    <div class="model-note pool-reminder">
      Round ${meta.round} pool reminder: signing bonuses up to ${formatMoney(POST_TENTH_ROUND_SLOT)} do not count against the pool. Only the amount above ${formatMoney(POST_TENTH_ROUND_SLOT)} counts.
    </div>
  ` : "";
  elements.controlledBadge.textContent = controlled ? "User" : "AI";
  elements.pickCard.innerHTML = `
    <div class="team-clock" style="--team-color: ${slot.team.color}">
      <span>${meta.roundLabel} · Pick ${slot.pick}${meta.competitiveBalance ? " · Competitive Balance" : ""}</span>
      <strong>${teamLogo(slot.team, "team-logo clock-logo")}${slot.team.name}</strong>
      <small>Needs: ${slot.team.needs.join(", ")}</small>
    </div>
    <div class="context-item">
      <span>Recommended pick</span>
      <strong>${best ? best.name : "No player available"}</strong>
    </div>
    <div class="context-item">
      <span>PG board value</span>
      <strong>${best ? `No. ${best.rank} overall` : "--"}</strong>
    </div>
    <div class="context-item">
      <span>Pick slot</span>
      <strong>${formatMoney(currentSlotValue)}</strong>
    </div>
    <div class="context-item">
      <span>${controlled ? "Best player ask" : "Team pool room"}</span>
      <strong>${controlled && best ? `${formatMoney(bestAsk)} (${formatSlotSavings(currentSlotValue - bestAsk)})` : formatMoney(remaining)}</strong>
    </div>
    ${postTenthReminder}
    <div class="model-note">
      ${controlled ? "Select a player from the board, or use Auto Pick For Me to take the best fit by team need." : `AI is making picks at ${(state.speed / 1000).toFixed(2)}s per pick. Adjust the speed slider any time.`}
    </div>
  `;
}

function renderResults() {
  renderResultsTabs();
  let filteredPicks = state.resultsView === "mine" ? state.picks.filter(pick => pick.source === "user") : state.picks;
  if (state.activeResultsTeam !== "all") {
    filteredPicks = filteredPicks.filter(pick => pick.teamId === state.activeResultsTeam);
  }
  const visiblePicks = filteredPicks;
  elements.gradeLegend.textContent = state.activeResultsTeam === "all" ? `${visiblePicks.length || 0} shown` : `${state.activeResultsTeam} ${visiblePicks.length || 0}`;
  renderPickRows(
    elements.resultsBody,
    visiblePicks,
    state.resultsView === "mine" ? "No controlled-team picks yet. The AI will pause when one of your teams is on the clock." : "No picks yet. Start the draft and the AI will run every non-controlled selection."
  );
  requestAnimationFrame(() => {
    const wrap = document.querySelector(".results-scroll");
    if (wrap) wrap.scrollTop = wrap.scrollHeight;
  });
}

function renderResultsTabs() {
  const controlled = Array.from(controlledTeams());
  const tabs = [`<button type="button" data-results-team="all" class="${state.activeResultsTeam === "all" ? "active" : ""}">All</button>`]
    .concat(controlled.map(teamId => {
      const count = state.picks.filter(pick => pick.teamId === teamId && pick.source === "user").length;
      return `<button type="button" data-results-team="${teamId}" class="${state.activeResultsTeam === teamId ? "active" : ""}">${teamId} <span>${count}</span></button>`;
    }));
  elements.resultsTabs.innerHTML = tabs.join("");
}

function renderFullResults() {
  let picks = state.picks;
  if (state.fullResultsRound !== "ALL") {
    picks = picks.filter(pick => (pick.round || pickMeta(pick.pick).round) === state.fullResultsRound);
  } else if (state.fullResultsTeam !== "ALL") {
    picks = picks.filter(pick => pick.teamId === state.fullResultsTeam);
  }
  renderPickRows(elements.fullResultsBody, picks, state.fullResultsRound !== "ALL" ? "No picks to show for that round yet." : "No picks to show yet.");
}

function renderPickRows(tbody, picks, emptyText) {
  tbody.textContent = "";
  if (!picks.length) {
    const row = document.createElement("tr");
    row.className = "empty-row";
    const cell = document.createElement("td");
    cell.colSpan = 15;
    cell.textContent = emptyText;
    row.appendChild(cell);
    tbody.appendChild(row);
    return;
  }

  picks.forEach(pick => {
    const row = document.createElement("tr");
    pickRowCells(pick).forEach(cell => {
      const td = document.createElement("td");
      if (cell.html) td.innerHTML = cell.html;
      else td.textContent = cell.value;
      if (cell.className) td.className = cell.className;
      row.appendChild(td);
    });
    tbody.appendChild(row);
  });
}

function pickRowCells(pick) {
  const team = teams.find(item => item.id === pick.teamId);
  const player = players.find(item => item.id === pick.playerId);
  const grade = pick.grade || { delta: 0, letter: "--", tone: "" };
  const meta = pick.round ? pick : pickMeta(pick.pick);
  return [
    { value: meta.round },
    { value: pick.pick },
    { value: meta.competitiveBalance ? "Yes" : "No", className: meta.competitiveBalance ? "positive" : "" },
    { html: `<span class="team-cell">${teamLogo(team, "team-logo table-logo")}<span>${team?.id || pick.teamId}</span></span>` },
    { value: player?.name || "Unknown player" },
    { value: player?.position || "--" },
    { value: player?.rank || "--" },
    { value: positionRankLabel(player) },
    { value: formatMoneyShort(pick.slotValue || 0) },
    { value: formatMoneyShort(pick.bonus || 0) },
    { value: formatMoneyShort(pick.poolCharge || 0) },
    { value: formatDelta(grade.delta || 0), className: deltaTone(grade.delta || 0) },
    { value: grade.letter, className: gradeClass(grade.letter) || grade.tone },
    { value: pick.fit || "--" },
    { value: pick.source === "user" ? "User" : "AI" }
  ];
}

function renderContext() {
  const slot = currentSlot();
  const controlledCount = controlledTeams().size;
  const budgetSummary = controlledBudgetSummary();
  const controlledSelections = state.picks.filter(pick => pick.source === "user");
  const controlledAverage = controlledSelections.length
    ? controlledSelections.reduce((sum, pick) => sum + gradePoints(pick.grade.letter), 0) / controlledSelections.length
    : null;
  const budgetFailed = controlledBudgetFailed();
  const draftedPositions = state.picks.reduce((counts, pick) => {
    const player = players.find(item => item.id === pick.playerId);
    const primary = player.position.split("/")[0];
    counts[primary] = (counts[primary] || 0) + 1;
    return counts;
  }, {});
  const mostDrafted = Object.entries(draftedPositions).sort((a, b) => b[1] - a[1])[0];

  elements.draftContext.innerHTML = `
    <div class="context-item">
      <span>Draft order</span>
      <strong>${activeDraftLength()} picks</strong>
    </div>
    <div class="context-item">
      <span>Controlled teams</span>
      <strong>${state.teamMode === "all" ? "All clubs" : controlledCount}</strong>
    </div>
    <div class="context-item">
      <span>Draft status</span>
      <strong>${!state.started ? "Not started" : isDraftComplete() ? "Complete" : slot ? (isUserControlled(slot.team.id) ? "User pick" : "AI pick") : "Complete"}</strong>
    </div>
    <div class="context-item">
      <span>Overall grade</span>
      <strong class="${gradeClass(budgetFailed ? "F" : controlledAverage ? letterFromPoints(controlledAverage) : "--")}">${budgetFailed ? "F" : controlledAverage ? letterFromPoints(controlledAverage) : "--"}</strong>
    </div>
    <div class="context-item">
      <span>Controlled pool</span>
      <strong>${state.started ? `${formatMoneyShort(budgetSummary.remaining)} left` : "Starts at draft"}</strong>
    </div>
    <div class="context-item">
      <span>Pool basis</span>
      <strong>Full 400 picks</strong>
    </div>
    <div class="context-item">
      <span>Most drafted position</span>
      <strong>${mostDrafted ? `${mostDrafted[0]} (${mostDrafted[1]})` : "None yet"}</strong>
    </div>
    <div class="model-note">
      Each controlled team starts with a bonus pool equal to its pick slot values. Player asks are modeled from recent signed-bonus behavior: top college players often come in under slot, premium high-school players can hold firmer numbers, and late college picks are frequently deep underslot. Picks after the 10th round can sign for up to $150k without counting against the pool; only the overage counts.
    </div>
  `;
}

function gradePoints(letter) {
  return { A: 4, B: 3, C: 2, D: 1, F: 0 }[letter] || 0;
}

function gradeClass(letter) {
  if (letter === "A") return "grade-a";
  if (letter === "F") return "grade-f";
  return "";
}

function letterFromPoints(points) {
  if (points >= 3.5) return "A";
  if (points >= 2.5) return "B";
  if (points >= 1.5) return "C";
  if (points >= 0.75) return "D";
  return "F";
}

function formatDelta(delta) {
  if (delta > 0) return `+${delta}`;
  return `${delta}`;
}

function formatMoney(value) {
  return value.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });
}

function formatMoneyShort(value) {
  const sign = value < 0 ? "-" : "";
  const amount = Math.abs(value);
  if (amount >= 1000000) return `${sign}$${(amount / 1000000).toFixed(1)}M`;
  if (amount >= 1000) return `${sign}$${Math.round(amount / 1000)}K`;
  return `${sign}$${amount.toLocaleString()}`;
}

function formatSlotSavings(value) {
  if (value >= 0) return `Save ${formatMoneyShort(value)}`;
  return `Over slot ${formatMoneyShort(Math.abs(value))}`;
}

function deltaTone(delta) {
  if (delta > 0) return "positive";
  if (delta < -2) return "negative";
  return "";
}

elements.teamMode.addEventListener("change", event => {
  state.teamMode = event.target.value;
  if (state.teamMode === "single") state.controlledTeamIds = new Set([state.primaryTeamId]);
  render();
});

elements.teamSelect.addEventListener("change", event => {
  state.primaryTeamId = event.target.value;
  if (state.teamMode === "single") state.controlledTeamIds = new Set([state.primaryTeamId]);
  else state.controlledTeamIds.add(state.primaryTeamId);
  render();
});

elements.roundSelect.addEventListener("change", event => {
  state.roundsToSim = event.target.value === "full" ? "full" : Number(event.target.value);
  state.demands = createDemands();
  state.budgets = createBudgets();
  render();
});

elements.controlledTeams.addEventListener("change", event => {
  const teamId = event.target.value;
  if (!teamId || state.teamMode !== "multi") return;
  if (event.target.checked) state.controlledTeamIds.add(teamId);
  else state.controlledTeamIds.delete(teamId);
  if (!state.controlledTeamIds.size) state.controlledTeamIds.add(state.primaryTeamId);
  render();
});

elements.speedSlider.addEventListener("input", event => {
  state.speed = speedForSliderValue(event.target.value);
  renderSpeedLabel();
});

elements.resultsView.addEventListener("change", event => {
  state.resultsView = event.target.value;
  renderResults();
});

elements.resultsTabs.addEventListener("click", event => {
  const button = event.target.closest("[data-results-team]");
  if (!button) return;
  state.activeResultsTeam = button.dataset.resultsTeam;
  renderResults();
});

elements.fullResultsTeam.addEventListener("change", event => {
  state.fullResultsTeam = event.target.value;
  renderFullResults();
});

elements.fullResultsRound.addEventListener("change", event => {
  state.fullResultsRound = event.target.value;
  renderControls();
  renderFullResults();
});

elements.playerSearch.addEventListener("input", event => {
  state.query = event.target.value;
  renderPlayerBoard();
});

elements.positionFilter.addEventListener("change", event => {
  state.position = event.target.value;
  renderPlayerBoard();
});

elements.typeFilter.addEventListener("change", event => {
  state.type = event.target.value;
  renderPlayerBoard();
});

elements.roleFilter.addEventListener("change", event => {
  state.role = event.target.value;
  renderPlayerBoard();
});

elements.playerBoard.addEventListener("click", event => {
  const button = event.target.closest("[data-player-id]");
  if (!button) return;
  handlePlayerInput(button.dataset.playerId, event);
});

elements.playerBoard.addEventListener("pointerdown", event => {
  const button = event.target.closest("[data-player-id]");
  if (!button || button.disabled) return;
  handlePlayerInput(button.dataset.playerId, event);
});

elements.autoPick.addEventListener("click", autoPick);
elements.undoPick.addEventListener("click", undoPick);
elements.resetDraft.addEventListener("click", resetDraft);
elements.startDraft.addEventListener("click", handleStartInput);
elements.startDraft.addEventListener("pointerdown", handleStartInput);
elements.startDraft.addEventListener("mousedown", handleStartInput);
elements.startDraft.addEventListener("touchstart", handleStartInput);
elements.startDraft.onpointerdown = handleStartInput;
elements.startDraft.onmousedown = handleStartInput;
elements.startDraft.ontouchstart = handleStartInput;
elements.startDraft.onclick = handleStartInput;
document.addEventListener("click", handleDraftAction, true);
document.addEventListener("pointerdown", handleDraftAction, true);
document.addEventListener("mousedown", handleDraftAction, true);
document.addEventListener("touchstart", handleDraftAction, true);
window.addEventListener("hashchange", handleActionHash);
window.setInterval(handleActionHash, 120);

window.DraftApp = {
  start: event => handleStartInput(event),
  pick: (playerId, event) => handlePlayerInput(playerId, event),
  snapshot: () => ({
    started: state.started,
    completed: state.completed,
    pickIndex: state.pickIndex,
    picks: state.picks.length,
    currentTeam: currentSlot()?.team.id || null,
    controlledTeams: Array.from(controlledTeams()),
    budgets: Object.fromEntries(Object.entries(state.budgets).map(([teamId, budget]) => [
      teamId,
      { total: budget.total, spent: budget.spent, remaining: budget.total - budget.spent }
    ]))
  })
};
window.startDraft = startDraft;
window.pickPlayer = pickPlayer;

state.demands = createDemands();
state.budgets = createBudgets();
render();
