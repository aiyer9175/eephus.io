(function () {
  "use strict";

  const MLB_STANDINGS_URL = "https://statsapi.mlb.com/api/v1/standings?leagueId=103,104&season=2026&standingsTypes=regularSeason";
  const FG_LEADERS_URL = "https://www.fangraphs.com/api/leaders/major-league/data";
  const LOTTERY_ODDS = [16.5, 16.5, 16.5, 13.25, 10.0, 7.48, 5.54, 3.90, 2.70, 1.79, 1.39, 1.09, 0.90, 0.76, 0.62, 0.48, 0.36, 0.23];
  const LOGO_IDS = {
    ARI: 109, ATL: 144, BAL: 110, BOS: 111, CHC: 112, CHW: 145, CIN: 113, CLE: 114, COL: 115, DET: 116,
    HOU: 117, KC: 118, LAA: 108, LAD: 119, MIA: 146, MIL: 158, MIN: 142, NYM: 121, NYY: 147, OAK: 133,
    PHI: 143, PIT: 134, SD: 135, SEA: 136, SF: 137, STL: 138, TB: 139, TEX: 140, TOR: 141, WSH: 120
  };
  const TEAM_ID_BY_MLBAM = Object.fromEntries(Object.entries(LOGO_IDS).map(([abbr, id]) => [String(id), abbr]));
  const TEAM_NAMES = {
    ARI: "Arizona Diamondbacks", ATL: "Atlanta Braves", BAL: "Baltimore Orioles", BOS: "Boston Red Sox",
    CHC: "Chicago Cubs", CHW: "Chicago White Sox", CIN: "Cincinnati Reds", CLE: "Cleveland Guardians",
    COL: "Colorado Rockies", DET: "Detroit Tigers", HOU: "Houston Astros", KC: "Kansas City Royals",
    LAA: "Los Angeles Angels", LAD: "Los Angeles Dodgers", MIA: "Miami Marlins", MIL: "Milwaukee Brewers",
    MIN: "Minnesota Twins", NYM: "New York Mets", NYY: "New York Yankees", OAK: "Athletics",
    PHI: "Philadelphia Phillies", PIT: "Pittsburgh Pirates", SD: "San Diego Padres", SEA: "Seattle Mariners",
    SF: "San Francisco Giants", STL: "St. Louis Cardinals", TB: "Tampa Bay Rays", TEX: "Texas Rangers",
    TOR: "Toronto Blue Jays", WSH: "Washington Nationals"
  };

  const LOTTERY_ELIGIBILITY_2027 = {
    SF: "CBA top-six cap: non-revenue-sharing clubs cannot receive lottery picks in consecutive years."
  };

  const CBT_PENALTY_TEAMS = {
    LAD: "Projected above the second CBT surcharge threshold",
    NYM: "Projected above the second CBT surcharge threshold",
    NYY: "Projected above the second CBT surcharge threshold",
    PHI: "Projected above the second CBT surcharge threshold",
    TOR: "Projected above the second CBT surcharge threshold"
  };

  const PPI_FALLBACK_ROOKIES = [
    { player: "Kevin McGonigle", team: "DET", league: "AL", war: null, source: "fallback watchlist" },
    { player: "Travis Bazzana", team: "CLE", league: "AL", war: null, source: "fallback watchlist" },
    { player: "Parker Messick", team: "CLE", league: "AL", war: null, source: "fallback watchlist" },
    { player: "JJ Wetherholt", aliases: ["J.J. Wetherholt", "Jonathan Wetherholt"], team: "STL", league: "NL", war: null, source: "fallback watchlist" },
    { player: "Sal Stewart", team: "CIN", league: "NL", war: null, source: "fallback watchlist" },
    { player: "A.J. Ewing", team: "NYM", league: "NL", war: null, source: "fallback watchlist" }
  ];

  const COMPETITIVE_BALANCE_ROUNDS = [
    {
      section: "Competitive Balance Round A",
      teams: ["CLE", "KC", "ARI", "STL", "BAL", "PIT", "COL"]
    },
    {
      section: "Competitive Balance Round B (after second round)",
      teams: ["MIL", "SEA", "DET", "CIN", "MIA", "TB", "OAK", "MIN"]
    }
  ];

  const state = {
    rows: [],
    rookies: [],
    rookieSource: "FanGraphs pending",
    loading: false,
    rookiesLoading: false,
    lastLoaded: null,
    lastOrder: []
  };

  const elements = {
    generateBtn: document.querySelector("#generateBtn"),
    refreshBtn: document.querySelector("#refreshBtn"),
    recordStatus: document.querySelector("#recordStatus"),
    ppiStatus: document.querySelector("#ppiStatus"),
    pickCount: document.querySelector("#pickCount"),
    generatedAt: document.querySelector("#generatedAt"),
    orderBoard: document.querySelector("#orderBoard"),
    ppiBoard: document.querySelector("#ppiBoard"),
    taxBoard: document.querySelector("#taxBoard"),
    rulesList: document.querySelector("#rulesList")
  };

  function esc(value) {
    return String(value == null ? "" : value).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  function stripHtml(value) {
    return String(value == null ? "" : value).replace(/<[^>]*>/g, "").replace(/&amp;/g, "&").trim();
  }

  function normalizedName(value) {
    return stripHtml(value).toLowerCase().replace(/[^a-z0-9]+/g, "");
  }

  function watchedRookieFor(player) {
    const key = normalizedName(player);
    return PPI_FALLBACK_ROOKIES.find(item => {
      const names = [item.player].concat(item.aliases || []);
      return names.some(name => normalizedName(name) === key);
    }) || null;
  }

  function logo(team) {
    const id = LOGO_IDS[team];
    return id ? `<img class="team-logo" src="https://www.mlbstatic.com/team-logos/${id}.svg" alt="${esc(TEAM_NAMES[team] || team)} logo" loading="lazy" />` : "";
  }

  function recordSort(a, b) {
    if (a.pct !== b.pct) return a.pct - b.pct;
    if (a.wins !== b.wins) return a.wins - b.wins;
    if (a.losses !== b.losses) return b.losses - a.losses;
    return a.team.localeCompare(b.team);
  }

  function playoffSort(a, b) {
    if (a.pct !== b.pct) return a.pct - b.pct;
    return a.team.localeCompare(b.team);
  }

  function bestRecordSort(a, b) {
    if (a.pct !== b.pct) return b.pct - a.pct;
    if (a.wins !== b.wins) return b.wins - a.wins;
    if (a.losses !== b.losses) return a.losses - b.losses;
    return a.team.localeCompare(b.team);
  }

  function markProjectedPlayoffTeams(rows) {
    const byLeague = rows.reduce((acc, row) => {
      (acc[row.leagueId] ||= []).push(row);
      return acc;
    }, {});
    Object.values(byLeague).forEach(leagueRows => {
      const byDivision = leagueRows.reduce((acc, row) => {
        (acc[row.divisionId] ||= []).push(row);
        return acc;
      }, {});
      const leaders = new Set();
      Object.values(byDivision).forEach(divisionRows => {
        const leader = divisionRows.slice().sort((a, b) => b.pct - a.pct || a.losses - b.losses)[0];
        if (leader) {
          leader.projectedPlayoff = true;
          leaders.add(leader.team);
        }
      });
      leagueRows
        .filter(row => !leaders.has(row.team))
        .sort((a, b) => b.pct - a.pct || a.losses - b.losses)
        .slice(0, 3)
        .forEach(row => { row.projectedPlayoff = true; });
    });
  }

  function standingsRows(data) {
    const rows = [];
    (data.records || []).forEach(group => {
      (group.teamRecords || []).forEach(record => {
        const team = TEAM_ID_BY_MLBAM[String(record.team?.id)];
        if (!team) return;
        const wins = Number(record.wins || 0);
        const losses = Number(record.losses || 0);
        rows.push({
          team,
          wins,
          losses,
          pct: wins / Math.max(1, wins + losses),
          leagueId: String(record.league?.id || group.league?.id || ""),
          divisionId: String(record.division?.id || group.division?.id || ""),
          projectedPlayoff: false
        });
      });
    });
    markProjectedPlayoffTeams(rows);
    return rows;
  }

  function fgParams(stats) {
    const params = new URLSearchParams({
      pos: "all",
      stats,
      lg: "all",
      qual: "0",
      season: "2026",
      season1: "2026",
      month: "0",
      team: "0",
      pageitems: "5000",
      pagenum: "1",
      ind: "0",
      rost: "0",
      type: "8",
      sortdir: "default",
      sortstat: "WAR"
    });
    return `${FG_LEADERS_URL}?${params.toString()}`;
  }

  function leagueFromRow(row) {
    const league = row.League || row.Lg || row.league || "";
    if (String(league).toUpperCase().includes("AL")) return "AL";
    if (String(league).toUpperCase().includes("NL")) return "NL";
    const team = stripHtml(row.Team || row.team || row.teamNameAbb || row.TeamNameAbb || "");
    const alTeams = new Set(["BAL", "BOS", "NYY", "TB", "TOR", "CHW", "CLE", "DET", "KC", "MIN", "HOU", "LAA", "OAK", "SEA", "TEX"]);
    return alTeams.has(String(team).toUpperCase()) ? "AL" : "NL";
  }

  function normalizeFgRow(row, side) {
    const player = stripHtml(row.PlayerName || row.Player || row.playerName || row.Name || "");
    const team = stripHtml(row.Team || row.team || row.teamNameAbb || row.TeamNameAbb || "").toUpperCase();
    const war = Number(row.WAR ?? row.war ?? row.FWAR ?? row.fWAR);
    const rookieFlag = row.Rookie ?? row.IsRookie ?? row.isRookie ?? row.Rk;
    const rookieText = String(rookieFlag == null ? "" : rookieFlag).toLowerCase();
    const watchedRookie = watchedRookieFor(player);
    const isRookie = rookieFlag === true || rookieFlag === 1 || rookieText === "true" || rookieText === "yes" || rookieText === "y" || rookieText === "rookie" || watchedRookie;
    if (!player || !team || !Number.isFinite(war) || !isRookie) return null;
    return { player: watchedRookie?.player || player, team, war, side, league: leagueFromRow(row), source: "FanGraphs" };
  }

  async function fetchFgLeaderboard(stats) {
    const response = await fetch(fgParams(stats), { cache: "no-cache" });
    if (!response.ok) throw new Error(`FanGraphs ${stats} HTTP ${response.status}`);
    const data = await response.json();
    const rows = Array.isArray(data) ? data : data.data || [];
    return rows.map(row => normalizeFgRow(row, stats === "pit" ? "P" : "B")).filter(Boolean);
  }

  async function refreshRookieWar() {
    state.rookiesLoading = true;
    renderStatus();
    try {
      const rows = (await Promise.all([fetchFgLeaderboard("bat"), fetchFgLeaderboard("pit")])).flat();
      if (!rows.length) throw new Error("No rookie rows returned");
      state.rookies = rows.sort((a, b) => b.war - a.war);
      state.rookieSource = "FanGraphs fWAR";
    } catch (error) {
      console.warn("Could not load FanGraphs rookie fWAR", error);
      state.rookies = PPI_FALLBACK_ROOKIES.slice();
      state.rookieSource = "Fallback PPI watchlist";
    } finally {
      state.rookiesLoading = false;
      renderPpiBoard();
      renderStatus();
    }
  }

  function lotteryPool(rows) {
    return rows
      .filter(row => !row.projectedPlayoff)
      .sort(recordSort)
      .map((row, index) => ({
        ...row,
        seed: index + 1,
        eligible: !LOTTERY_ELIGIBILITY_2027[row.team],
        baseOdds: LOTTERY_ODDS[index] || 0,
        reason: LOTTERY_ELIGIBILITY_2027[row.team] || ""
      }));
  }

  function weightedDraw(pool) {
    const total = pool.reduce((sum, row) => sum + row.baseOdds, 0);
    let ticket = Math.random() * total;
    for (const row of pool) {
      ticket -= row.baseOdds;
      if (ticket <= 0) return row;
    }
    return pool[pool.length - 1];
  }

  function drawLottery(pool) {
    const candidates = pool.filter(row => row.eligible && row.baseOdds > 0);
    const winners = [];
    while (winners.length < 6 && candidates.length) {
      const winner = weightedDraw(candidates);
      winners.push(winner);
      candidates.splice(candidates.findIndex(row => row.team === winner.team), 1);
    }
    return winners;
  }

  function projectedPpiPicks(startPick) {
    const picks = [];
    const usedTeams = new Set();
    ["AL", "NL"].forEach(league => {
      const leader = state.rookies
        .filter(row => row.league === league && !usedTeams.has(row.team))
        .sort((a, b) => (b.war ?? -999) - (a.war ?? -999))[0];
      if (!leader) return;
      usedTeams.add(leader.team);
      picks.push({
        pick: startPick + picks.length,
        team: leader.team,
        section: `Projected PPI (${league} rookie fWAR leader)`,
        record: leader.war == null ? leader.player : `${leader.player}, ${leader.war.toFixed(1)} fWAR`,
        odds: null,
        className: "ppi",
        player: leader.player
      });
    });
    return picks;
  }

  function competitiveBalancePicks(startPick) {
    const rowsByTeam = new Map(state.rows.map(row => [row.team, row]));
    const picks = [];
    COMPETITIVE_BALANCE_ROUNDS.forEach(round => {
      round.teams
        .map(team => rowsByTeam.get(team) || { team, wins: 0, losses: 0, pct: 0 })
        .sort(bestRecordSort)
        .forEach(row => {
          picks.push({
            pick: startPick + picks.length,
            team: row.team,
            section: round.section,
            record: rowsByTeam.has(row.team) ? `${row.wins}-${row.losses}` : "Record unavailable",
            odds: null,
            className: "comp"
          });
        });
    });
    return picks;
  }

  function renumber(order) {
    order.forEach((item, index) => {
      item.pick = index + 1;
    });
    return order;
  }

  function applyCbtPenalties(order) {
    Object.entries(CBT_PENALTY_TEAMS).forEach(([team, reason]) => {
      const indexes = order
        .map((item, index) => ({ item, index }))
        .filter(entry => entry.item.team === team);
      if (!indexes.length) return;
      let target = indexes[0];
      if (target.index < 6 && indexes[1]) target = indexes[1];
      const [item] = order.splice(target.index, 1);
      item.section = `${item.section} - CBT 10-slot drop`;
      item.className = `${item.className || ""} tax-drop`.trim();
      item.taxPenalty = reason;
      const nextIndex = Math.min(order.length, target.index + 10);
      order.splice(nextIndex, 0, item);
    });
    return renumber(order);
  }

  function buildOrder() {
    const pool = lotteryPool(state.rows);
    const lotteryWinners = drawLottery(pool);
    const selected = new Set(lotteryWinners.map(row => row.team));
    const firstRound = lotteryWinners.map((row, index) => ({
      pick: index + 1,
      team: row.team,
      section: "Lottery",
      record: `${row.wins}-${row.losses}`,
      odds: row.baseOdds,
      className: "lottery"
    }));

    const capped = [];
    pool.filter(row => !selected.has(row.team)).sort(recordSort).forEach(row => {
      const item = {
        team: row.team,
        section: row.eligible ? "Non-playoff" : "CBA capped",
        record: `${row.wins}-${row.losses}`,
        odds: row.eligible ? null : 0,
        className: row.eligible ? "" : "comp"
      };
      if (!row.eligible && firstRound.length < 9) capped.push(item);
      else firstRound.push({ ...item, pick: firstRound.length + 1 });
    });
    capped.forEach(item => firstRound.push({ ...item, pick: firstRound.length + 1 }));

    state.rows
      .filter(row => row.projectedPlayoff)
      .sort(playoffSort)
      .forEach(row => {
        firstRound.push({
          pick: firstRound.length + 1,
          team: row.team,
          section: "Projected playoff",
          record: `${row.wins}-${row.losses}`,
          odds: null,
          className: ""
        });
      });

    const ppi = projectedPpiPicks(firstRound.length + 1);
    const afterPpi = firstRound.concat(ppi);
    const competitiveBalance = competitiveBalancePicks(afterPpi.length + 1);
    return applyCbtPenalties(afterPpi.concat(competitiveBalance));
  }

  function renderOrder(order) {
    elements.pickCount.textContent = `${order.length} picks`;
    elements.orderBoard.innerHTML = order.map(item => `
      <article class="pick-card ${item.className}">
        <div class="pick-no">${item.pick}</div>
        <div>
          <div class="team-line">${logo(item.team)}<span class="team-name">${esc(TEAM_NAMES[item.team] || item.team)}</span></div>
          <div class="pick-sub">${esc(item.section)} - ${esc(item.record)}</div>
          ${item.taxPenalty ? `<div class="pick-sub">${esc(item.taxPenalty)}</div>` : ""}
        </div>
        <div class="odds">${item.odds == null ? "" : `${item.odds.toFixed(2)}%`}</div>
      </article>
    `).join("");
  }

  function renderPpiBoard() {
    if (!state.rookies.length) {
      elements.ppiBoard.innerHTML = `<div class="rule-note">Rookie fWAR leaders have not loaded yet.</div>`;
      return;
    }
    const leaders = ["AL", "NL"].map(league => state.rookies
      .filter(row => row.league === league)
      .sort((a, b) => (b.war ?? -999) - (a.war ?? -999))[0]
    ).filter(Boolean);
    elements.ppiBoard.innerHTML = leaders.map(row => `
      <div class="mini-row">
        <span>${esc(row.league)} - ${esc(row.player)} (${esc(row.team)})</span>
        <strong>${row.war == null ? row.source : `${row.war.toFixed(1)} fWAR`}</strong>
      </div>
    `).join("");
  }

  function renderTaxBoard() {
    elements.taxBoard.innerHTML = Object.entries(CBT_PENALTY_TEAMS).map(([team, reason]) => `
      <div class="mini-row">
        <span>${esc(team)} - ${esc(TEAM_NAMES[team] || team)}</span>
        <strong>${esc(reason.replace("Projected ", ""))}</strong>
      </div>
    `).join("");
  }

  function renderRules() {
    elements.rulesList.innerHTML = [
      "Generate draws six lottery picks from the 18 projected non-playoff teams using MLB's published seed odds.",
      "The remaining non-playoff teams follow reverse current record; projected playoff teams follow reverse current record after them.",
      "The playoff field is projected in-season as division leaders plus three wild cards per league.",
      "San Francisco is capped from the lottery in this 2027 model because it drew a top-six pick in 2026 as a non-revenue-sharing club.",
      "Projected PPI picks are assigned to the current AL and NL rookie fWAR leaders, one pick per club, as an award-proxy rather than a final award result.",
      "Teams projected above the second CBT surcharge threshold have their first pick moved back 10 places; top-six first picks are protected, shifting the penalty to that team's second-highest pick.",
      "Competitive Balance Round A uses the seven listed smallest-market clubs and is ordered by current record, best to worst, after the first-round/PPI area.",
      "Competitive Balance Round B uses the remaining eight listed smallest-market clubs and is ordered by current record, best to worst, after the second round."
    ].map(text => `<div class="rule-note">${esc(text)}</div>`).join("");
  }

  function renderStatus() {
    elements.generateBtn.disabled = state.loading || state.rookiesLoading || state.rows.length < 30;
    elements.refreshBtn.disabled = state.loading;
    elements.ppiStatus.textContent = state.rookiesLoading ? "Loading..." : state.rookies.length ? state.rookieSource : "Unavailable";
    if (state.loading) {
      elements.recordStatus.textContent = "Loading...";
    } else if (state.rows.length >= 30) {
      elements.recordStatus.textContent = `Loaded ${state.lastLoaded}`;
    } else {
      elements.recordStatus.textContent = "Unavailable";
    }
  }

  async function refreshRecords() {
    state.loading = true;
    renderStatus();
    try {
      const response = await fetch(MLB_STANDINGS_URL, { cache: "no-cache" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      const rows = standingsRows(data);
      if (rows.length < 30) throw new Error("Incomplete standings");
      state.rows = rows;
      state.lastLoaded = new Date().toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
    } catch (error) {
      console.warn("Could not load MLB standings", error);
      state.rows = [];
    } finally {
      state.loading = false;
      renderStatus();
    }
  }

  function generateOrder() {
    if (state.rows.length < 30) return;
    state.lastOrder = buildOrder();
    elements.generatedAt.textContent = new Date().toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
    renderOrder(state.lastOrder);
    renderStatus();
  }

  elements.generateBtn.addEventListener("click", generateOrder);
  elements.refreshBtn.addEventListener("click", () => {
    refreshRecords();
    refreshRookieWar();
  });
  renderTaxBoard();
  renderPpiBoard();
  renderRules();
  renderStatus();
  refreshRecords();
  refreshRookieWar();
})();
