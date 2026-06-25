(function () {
  const root = document.querySelector("[data-global-search]");
  if (!root) return;

  const input = root.querySelector("[data-global-search-input]");
  const results = root.querySelector("[data-global-search-results]");
  let allPlayers = buildGlobalIndex();

  // Cross-population data is no longer shipped at boot (the hitters page
  // skips pitcher_data.js and vice versa - 14-16MB each, search-only on
  // the opposite page). First interaction with the search box injects the
  // missing payload and rebuilds the index; until it arrives the index
  // covers the current page's population, so search degrades gracefully
  // instead of blocking first paint.
  let pendingLoad = null;
  function ensureFullIndex() {
    if (pendingLoad) return;
    const missing = [];
    if (!window.HITTER_DATA) missing.push("hitter_year_data.js");
    if (!window.PITCHER_DATA) missing.push("pitcher_data.js");
    if (!missing.length) return;
    pendingLoad = Promise.all(missing.map(injectScript))
      .then(() => {
        allPlayers = buildGlobalIndex();
        if (input.value.trim().length >= 2) renderResults(input.value);
      })
      .catch(() => { pendingLoad = null; });  // retry on next focus
  }

  function injectScript(src) {
    return new Promise((resolve, reject) => {
      const s = document.createElement("script");
      s.src = src;
      s.onload = resolve;
      s.onerror = () => reject(new Error(`failed to load ${src}`));
      document.head.appendChild(s);
    });
  }

  input.addEventListener("input", () => { ensureFullIndex(); renderResults(input.value); });
  input.addEventListener("focus", () => { ensureFullIndex(); renderResults(input.value); });
  input.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      input.value = "";
      hideResults();
      input.blur();
    }
  });

  document.addEventListener("click", (event) => {
    if (!root.contains(event.target)) hideResults();
  });

  function renderResults(query) {
    const term = query.trim().toLowerCase();
    if (term.length < 2) {
      hideResults();
      return;
    }

    const matches = allPlayers
      .filter((player) => player.search.includes(term))
      .sort((a, b) => {
        const aStarts = a.search.startsWith(term) ? 0 : 1;
        const bStarts = b.search.startsWith(term) ? 0 : 1;
        if (aStarts !== bStarts) return aStarts - bStarts;
        return a.name.localeCompare(b.name);
      })
      .slice(0, 10);

    if (!matches.length) {
      results.innerHTML = `<div class="global-result empty-result">No players found</div>`;
      root.classList.add("is-open");
      return;
    }

    results.innerHTML = matches.map((player) => `
      <a class="global-result" href="${player.href}">
        <span class="result-name">${escapeHtml(player.name)}</span>
        <span class="result-meta">${escapeHtml(player.kind)} - ${escapeHtml(player.team || "Team")}</span>
      </a>
    `).join("");
    root.classList.add("is-open");
  }

  function hideResults() {
    root.classList.remove("is-open");
    results.innerHTML = "";
  }

  function buildGlobalIndex() {
    const hitterRows = window.HITTER_DATA || parseHitterRows().map((row) => ({ ...row, year: 2025 }));
    const hitters = hitterRows.map((row) => {
      const slug = slugify(row.hitter_name);
      const year = Number(row.year || 2025);
      const teamCode = row.team || window.B1G_TEAMS?.[slug]?.team || "";
      const teamLabel = row.team || window.B1G_TEAMS?.[slug]?.label || teamCode;
      return {
        kind: "Hitter",
        name: displayName(row.hitter_name || ""),
        team: `${teamLabel || "Team"} ${year}`,
        href: `index.html#/player/${year}/${slug}`,
        search: `${row.hitter_name || ""} ${displayName(row.hitter_name || "")} ${teamCode} ${teamLabel} hitter ${year}`.toLowerCase(),
      };
    });

    const pitchers = (window.PITCHER_DATA || []).map((row) => {
      const slug = slugify(`${row.pitcher_name}-${row.pitcher_id}`);
      const year = Number(row.year || 2026);
      const teamLabel = formatPitcherTeamName(row.team);
      return {
        kind: "Pitcher",
        name: displayName(row.pitcher_name || ""),
        team: `${teamLabel || "Team"} ${year}`,
        href: `pitcher_index.html#/player/${year}/${slug}`,
        search: `${row.pitcher_name || ""} ${displayName(row.pitcher_name || "")} ${row.team || ""} ${teamLabel} pitcher ${year}`.toLowerCase(),
      };
    });

    return [...hitters, ...pitchers];
  }

  function parseHitterRows() {
    if (!window.B1G_CSV) return [];
    const rows = parseCsv(window.B1G_CSV);
    return rows.filter((row) => row.hitter_name);
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
    if (!headers) return [];
    return body.map((cells) =>
      Object.fromEntries(headers.map((header, index) => [header, cells[index] ?? ""]))
    );
  }

  function displayName(name) {
    const [last, first] = String(name).split(",").map((part) => part.trim());
    return first ? `${first} ${last}` : String(name);
  }

  function formatPitcherTeamName(team) {
    const code = String(team || "").trim();
    if (!code) return "Team";
    const full = {
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
      ILL_ILL: "Illinois Fighting Illini",
      IU: "Indiana Hoosiers",
      IOW_HAW: "Iowa Hawkeyes",
      MAR_TER: "Maryland Terrapins",
      MIC_SPA: "Michigan State Spartans",
      MIC_WOL: "Michigan Wolverines",
      MSU_BDG: "Mississippi State",
      NEB: "Nebraska Cornhuskers",
      NOR_CAT: "Northwestern Wildcats",
      ORE_DUC: "Oregon Ducks",
      OSU_BUC: "Ohio State Buckeyes",
      PEN_NIT: "Penn State Nittany Lions",
      PUR_BOI: "Purdue Boilermakers",
      RUT_SCA: "Rutgers Scarlet Knights",
      SOU_TRO: "USC Trojans",
      TEX_LON: "Texas Longhorns",
      WAS_HUS: "Washington Huskies",
    };
    if (full[code]) return full[code];
    return code.replace(/_/g, " ");
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
})();
