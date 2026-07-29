// Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
// Unauthorized copying of this file, via any medium is strictly prohibited
// Proprietary and confidential
// Written by Noah J. Dengler (@ARKNDJL), 2026
//
// /fantasy/ module app. Reads data/fantasy.json (fantasy_export.py): ROS
// projections with per-player counting-stat vectors, the four Ottoneu scoring
// systems' weight tables, the probable-pitcher schedule, and nine prebuilt
// sections (incl. eFV-derived Dynasty Prospects). The client re-scores the whole
// pool on the fly when the league
// scoring selector changes (points = dot product; roto = pool z-scores), so a
// user always sees ranks in THEIR format. Theme-tokened, EEPHUS_HUB player
// links, defensive load states (matches the mlbstats/pal smoke-test contract).
(function () {
  "use strict";
  var DATA_URL = "/data/fantasy.json";
  var S = { data: null, system: "fgp", section: "streamers", byId: {}, streamerDay: null };
  // player_links map (mlbam -> merged-card key), resolved once at boot so
  // nameLink can build hrefs synchronously (mirrors mlbstats.js / pal.js).
  var LINKS = null;

  // ---- helpers --------------------------------------------------------------
  function el(id) { return document.getElementById(id); }
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
    return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }
  function num(v, d) { return (v == null || isNaN(v)) ? "-" : Number(v).toFixed(d == null ? 1 : d); }
  function nameLink(mlbam, name) {
    var e = LINKS && LINKS.byMlbam && LINKS.byMlbam[String(mlbam)];
    if (e && e.key) return '<a class="fantasy-name-link" href="/projections/#player=' + esc(e.key) + '">' + esc(name) + "</a>";
    return esc(name);
  }
  function teamLogo(team) {
    return (window.EEPHUS_HUB && EEPHUS_HUB.teamLogo && team) ? EEPHUS_HUB.teamLogo(team) : "";
  }

  // ---- scoring (mirrors fantasy_scoring.py; recomputed client-side) ---------
  function scorePoints(ros, side) {
    if (!ros) return null;
    var sc = S.data.scoring || {};
    var w = side === "hit" ? sc.hitter : ((sc.pitcher || {})[S.system] || {});
    var t = 0;
    for (var k in w) if (ros[k] != null) t += ros[k] * w[k];
    return Math.round(t * 10) / 10;
  }
  var ROTO = {
    "5x5": { hit: ["avg", "hr", "rbi", "sb", "r"], pit: ["w", "sv", "era", "whip", "k"] },
    "4x4": { hit: ["obp", "slg", "hr", "r"], pit: ["era", "whip", "hr9", "k"] }
  };
  var RATE = { avg: 1, obp: 1, slg: 1, era: 1, whip: 1, hr9: 1 };
  var LOWER = { era: 1, whip: 1, hr9: 1 };
  function rotoValue(pool, side) {
    var cats = ROTO[S.system][side], ptk = side === "hit" ? "pa" : "ip";
    // PT-weighted pool mean for each rate cat.
    var means = {};
    cats.forEach(function (c) {
      if (!RATE[c]) return;
      var n = 0, d = 0;
      pool.forEach(function (p) { var r = p.ros || {}; n += (r[c] || 0) * (r[ptk] || 0); d += (r[ptk] || 0); });
      means[c] = d ? n / d : 0;
    });
    var raw = {}; cats.forEach(function (c) { raw[c] = []; });
    pool.forEach(function (p) {
      var r = p.ros || {};
      cats.forEach(function (c) {
        var v;
        if (RATE[c]) { var dev = (r[c] || 0) - means[c]; if (LOWER[c]) dev = -dev; v = dev * (r[ptk] || 0); }
        else v = r[c] || 0;
        raw[c].push(v);
      });
    });
    var z = {}; cats.forEach(function (c) {
      var xs = raw[c], mu = xs.reduce(function (a, b) { return a + b; }, 0) / (xs.length || 1);
      var sd = Math.sqrt(xs.reduce(function (a, b) { return a + (b - mu) * (b - mu); }, 0) / (xs.length || 1));
      z[c] = xs.map(function (x) { return sd ? (x - mu) / sd : 0; });
    });
    var out = {};
    pool.forEach(function (p, i) { var t = 0; cats.forEach(function (c) { t += z[c][i]; }); out[p.mlbam] = t; });
    return out;
  }
  function isRoto() { return S.system === "5x5" || S.system === "4x4"; }
  // Score every player in `ids` under the current system → [{p, score}] desc.
  function scored(ids, side) {
    var pool = ids.map(function (m) { return S.byId[m]; }).filter(Boolean);
    if (isRoto()) {
      var rv = rotoValue(pool, side);
      return pool.map(function (p) { return { p: p, score: rv[p.mlbam] }; })
                 .sort(function (a, b) { return b.score - a.score; });
    }
    return pool.map(function (p) { return { p: p, score: scorePoints(p.ros, side) }; })
               .sort(function (a, b) { return (b.score || -1e9) - (a.score || -1e9); });
  }
  function scoreLabel() { return isRoto() ? "Value" : (S.system === "sabr" ? "SABR pts" : "FG pts"); }

  // ---- section renderers ----------------------------------------------------
  function tableHitter(ids) {
    var rows = scored(ids, "hit").slice(0, 250).map(function (o, i) {
      var p = o.p, r = p.ros || {}, s = p.skill || {};
      return '<tr><td class="ff-rk">' + (i + 1) + '</td><td class="ff-nm">' + teamLogo(p.team) + " " + nameLink(p.mlbam, p.name) +
        '</td><td>' + esc(p.pos || "") + '</td><td class="ff-sc">' + num(o.score, isRoto() ? 2 : 0) + "</td>" +
        "<td>" + num(r.hr, 0) + "</td><td>" + num(r.r, 0) + "</td><td>" + num(r.rbi, 0) + "</td><td>" + num(r.sb, 0) +
        "</td><td>" + num(r.avg, 3) + "</td><td>" + num(r.obp, 3) + "</td><td>" + (s.hem_plus != null ? num(s.hem_plus, 0) : "-") + "</td></tr>";
    }).join("");
    return '<table class="fantasy-table"><thead><tr><th>#</th><th>Player</th><th>Pos</th><th>' + scoreLabel() +
      '</th><th>HR</th><th>R</th><th>RBI</th><th>SB</th><th>AVG</th><th>OBP</th><th class="g-term" data-gl="hem_plus">HEM+</th></tr></thead><tbody>' +
      rows + "</tbody></table>";
  }
  function tablePitcher(ids, isRp) {
    var rows = scored(ids, "pit").slice(0, 250).map(function (o, i) {
      var p = o.p, r = p.ros || {}, s = p.skill || {};
      var skillCell = isRp ? (s.rem_plus != null ? num(s.rem_plus, 0) : "-") : (s.sem_plus != null ? num(s.sem_plus, 0) : "-");
      var roleStat = isRp ? (num(r.sv, 0) + " SV") : (num(r.qs, 0) + " QS");
      return '<tr><td class="ff-rk">' + (i + 1) + '</td><td class="ff-nm">' + teamLogo(p.team) + " " + nameLink(p.mlbam, p.name) +
        '</td><td class="ff-sc">' + num(o.score, isRoto() ? 2 : 0) + "</td>" +
        "<td>" + num(r.ip, 0) + "</td><td>" + num(r.k, 0) + "</td><td>" + num(r.era, 2) + "</td><td>" + num(r.whip, 2) +
        "</td><td>" + roleStat + "</td><td class=\"g-term\" data-gl=\"" + (isRp ? "rem_plus" : "sem_plus") + "\">" + skillCell + "</td></tr>";
    }).join("");
    return '<table class="fantasy-table"><thead><tr><th>#</th><th>Player</th><th>' + scoreLabel() +
      '</th><th>IP</th><th>K</th><th>ERA</th><th>WHIP</th><th>' + (isRp ? "Saves" : "QS") + '</th><th>' +
      (isRp ? "REM+" : "SEM+") + "</th></tr></thead><tbody>" + rows + "</tbody></table>";
  }
  function streamerDayLabel(d) {
    // "2026-07-23" -> "Thu 7/23". Parse the parts locally (a bare ISO string
    // through new Date() is treated as UTC and can shift a day).
    var p = String(d || "").split("-");
    if (p.length !== 3) return esc(d);
    var dt = new Date(+p[0], +p[1] - 1, +p[2]);
    var wd = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"][dt.getDay()];
    return wd + " " + (+p[1]) + "/" + (+p[2]);
  }
  function tableStreamers(list) {
    // Group by date BEFORE any slice so one busy slate cannot starve later days;
    // each day is capped independently. One day renders at a time (date pills).
    var byDay = {}, days = [];
    (list || []).forEach(function (st) {
      var d = st.date || "";
      if (!byDay[d]) { byDay[d] = []; days.push(d); }
      byDay[d].push(st);
    });
    days.sort();
    if (!days.length) return '<div class="fantasy-note">Probables are not posted for the streamer window yet - check back once lineups firm up.</div>';
    if (!S.streamerDay || days.indexOf(S.streamerDay) < 0) S.streamerDay = days[0];
    var pills = days.map(function (d) {
      var on = d === S.streamerDay;
      return '<button type="button" class="ff-daypill' + (on ? " active" : "") + '" data-streamerday="' + esc(d) +
        '" role="tab" aria-selected="' + (on ? "true" : "false") + '">' + streamerDayLabel(d) + "</button>";
    }).join("");
    var rows = (byDay[S.streamerDay] || []).slice(0, 40).map(function (st, i) {
      var p = S.byId[st.mlbam] || {}, s = p.skill || {};
      return '<tr><td class="ff-rk">' + (i + 1) + '</td><td>' + esc(st.date) + '</td><td class="ff-nm">' +
        nameLink(st.mlbam, st.name) + " " + teamLogo(st.team) + '</td><td>@ ' + esc(st.opp_org) +
        " (Off+ " + num(st.opp_off, 0) + ')</td><td class="ff-sc">' + num(st.per_start_fgp, 1) + "</td><td>" +
        (s.sem_plus != null ? num(s.sem_plus, 0) : "-") + "</td><td>" + esc(st.venue || "") + "</td></tr>";
    }).join("");
    return '<div class="fantasy-note">Every announced probable start over the next 3 days, ranked by matchup-adjusted expected points (weaker opposing offense ranks higher). Pick a day below. Scored in FanGraphs Points; switch formats above to re-rank the ROS boards.</div>' +
      '<div class="ff-daypills" role="tablist" aria-label="Streamer day">' + pills + "</div>" +
      '<table class="fantasy-table"><thead><tr><th>#</th><th>Date</th><th>Pitcher</th><th>Opponent</th><th>Exp pts</th><th>SEM+</th><th>Park</th></tr></thead><tbody>' + rows + "</tbody></table>";
  }
  function tableTwoStart(list) {
    if (!list || !list.length) return '<div class="fantasy-note">No two-start pitchers detected or projectable in the current window yet - check back once probables post for the scoring week.</div>';
    var rows = list.slice(0, 60).map(function (t, i) {
      var legs = (t.legs || []).map(function (l) {
        var leg = "@" + esc(l.opp_org) + " (" + num(l.exp_fgp, 0) + ")";
        return l.projected ? '<span class="ff-proj">' + leg + " (proj)</span>" : leg;
      }).join(" · ");
      return '<tr><td class="ff-rk">' + (i + 1) + '</td><td class="ff-nm">' + nameLink(t.mlbam, t.name) + " " + teamLogo(t.team) +
        '</td><td>' + esc(t.n_starts) + '</td><td class="ff-sc">' + num(t.total_fgp, 1) + "</td><td>" + legs + "</td></tr>";
    }).join("");
    return '<div class="fantasy-note">Pitchers lined up for two starts this scoring week. MLB posts probables only ~5 days out, so the second start is projected from the team schedule on normal rest and marked (proj) until it is announced.</div>' +
      '<table class="fantasy-table"><thead><tr><th>#</th><th>Pitcher</th><th>Starts</th><th>Total pts</th><th>Matchups</th></tr></thead><tbody>' + rows + "</tbody></table>";
  }
  function renderBuySell() {
    function col(ids, label, cls) {
      var rows = (ids || []).slice(0, 30).map(function (m) {
        var p = S.byId[m]; if (!p) return "";
        var s = p.skill || {}, isHit = p.side === "hit", gap = isHit ? s.luck_gap : s.luck;
        // Mechanics-trend chip (W6, display context only): baked server-side
        // from per-season Swing+ when the latest-vs-prior move is >= 5 points.
        // Never part of the buy/sell ranking - the sort is luck-only.
        var mt = p.swing_trend, chip = "";
        if (mt && mt.delta != null) {
          var md = (mt.delta > 0 ? "+" : "") + num(mt.delta, 0);
          chip = ' <span class="ff-mech ' + (mt.delta > 0 ? "ff-mech-up" : "ff-mech-down") +
            '" title="Mechanics trend: per-season Swing+ (Will Cahoon) moved ' + md + " from " +
            esc(mt.from) + " to " + esc(mt.to) + '. Context only - never part of this ranking.">mech trend ' + md + "</span>";
        }
        // Hitter luck_gap is a plus-stat (0 decimals); pitcher luck is in wOBA
        // points (~0.03), so render 3 decimals or it collapses to "0".
        return "<tr><td class=\"ff-nm\">" + teamLogo(p.team) + " " + nameLink(p.mlbam, p.name) + chip + "</td><td>" + esc(p.pos || "") +
          '</td><td class="ff-sc ' + cls + '">' + (gap > 0 ? "+" : "") + num(gap, isHit ? 0 : 3) + "</td></tr>";
      }).join("");
      return '<div class="fantasy-half"><h3>' + label + '</h3><table class="fantasy-table"><thead><tr><th>Player</th><th>Pos</th><th>Luck gap</th></tr></thead><tbody>' + rows + "</tbody></table></div>";
    }
    var sec = S.data.sections || {};
    return '<div class="fantasy-note">Regression candidates from our expected-stat gaps (hitters: xHEM+ − HEM+; pitchers: xERA/xwOBA vs actual). A positive gap means the player has been UNLUCKY and is due to improve (buy); negative means overperforming (sell). A mech trend chip flags a 5+ point move in per-season Swing+ (Will Cahoon) - swing-mechanics context only, never part of the ranking.</div>' +
      '<div class="fantasy-cols">' + col(sec.buy_low, "Buy-Low (unlucky)", "ff-pos") + col(sec.sell_high, "Sell-High (overperforming)", "ff-neg") + "</div>";
  }
  function renderClosers() {
    var depth = (S.data.sections || {}).closer_depth || {};
    var teams = Object.keys(depth).sort();
    var cards = teams.map(function (tm) {
      var lst = (depth[tm] || []).map(function (m, i) {
        var p = S.byId[m]; if (!p) return "";
        var s = p.skill || {};
        var role = i === 0 ? '<span class="ff-closer">CLOSER</span>' : '<span class="ff-hc">' + (i === 1 ? "next" : "depth") + "</span>";
        return '<div class="ff-relief">' + role + " " + nameLink(p.mlbam, p.name) +
          ' <span class="ff-dim">gmLI ' + num(s.gmli, 2) + " · " + num(s.saves, 0) + "sv · REM+ " + num(s.rem_plus, 0) + "</span></div>";
      }).join("");
      return '<div class="fantasy-team-card"><div class="ff-team-hd">' + teamLogo(tm) + " " + esc(tm) + "</div>" + lst + "</div>";
    }).join("");
    return '<div class="fantasy-note">Bullpen pecking order by average leverage (gmLI) - the top arm is the likely closer, the rest are save handcuffs. Grab the next-in-line before the save chance opens.</div><div class="fantasy-grid">' + cards + "</div>";
  }
  function renderCallups() {
    var list = (S.data.sections || {}).callup_watch || [];
    if (!list.length) return '<div class="fantasy-note">Call-up watch populates from the PROSPX prospect board on the nightly build (fantasy-relevant prospects near their ETA).</div>';
    var rows = list.map(function (c) {
      return "<tr><td class=\"ff-nm\">" + nameLink(c.mlbam, c.name) + "</td><td>" + esc(c.org) + "</td><td>" + esc(c.pos) +
        "</td><td>" + esc(c.eta) + "</td><td>" + num(c.fv, 0) + "</td></tr>";
    }).join("");
    return '<div class="fantasy-note">Prospects near the majors with fantasy upside - stash before the call.</div>' +
      '<table class="fantasy-table"><thead><tr><th>Prospect</th><th>Org</th><th>Pos</th><th>ETA</th><th>FV</th></tr></thead><tbody>' + rows + "</tbody></table>";
  }
  function renderDynasty() {
    var list = (S.data.sections || {}).dynasty || [];
    if (!list.length) return '<div class="fantasy-note">Dynasty prospect rankings populate from the eFV model on the nightly build.</div>';
    var rows = list.map(function (d) {
      var band = d.band || [], outlook = (band[0] != null && band[1] != null) ?
        ("$" + num(band[0], 0) + "-" + num(band[1], 0) + "M") : "-";
      var tierCls = d.tier === "Elite" ? " ff-tier-elite" : (d.tier === "Tier 1" ? " ff-tier-one" : "");
      return '<tr><td class="ff-rk">' + esc(d.rank) + '</td><td class="ff-nm">' + teamLogo(d.org) + " " +
        nameLink(d.mlbam, d.name) + '</td><td>' + esc(d.pos || "") +
        '</td><td class="ff-sc">' + num(d.efv, 0) + '</td><td>' + esc(d.eta || "-") +
        '</td><td>' + num(d.star, 0) + '%</td><td>' + num(d.bust, 0) + '%</td><td>' + outlook +
        '</td><td><span class="ff-tier' + tierCls + '">' + esc(d.tier) + '</span></td></tr>';
    }).join("");
    return '<div class="fantasy-note">Dynasty prospect value from our flagship eFV model - ranked by a blend that keeps the eFV grade primary, then rewards star upside (star-outcome odds), penalizes floor risk (bust odds), and factors ETA proximity and projected surplus. Outlook is each prospect\'s 10th-to-90th percentile career-value band. This is a display ranking over served eFV numbers, not a separate model.</div>' +
      '<table class="fantasy-table"><thead><tr><th>#</th><th>Prospect</th><th>Pos</th><th class="g-term" data-gl="xfv">eFV</th><th>ETA</th>' +
      '<th class="g-term" data-gl="star_odds">Star</th><th class="g-term" data-gl="bust_prob">Bust</th><th>Outlook</th><th>Tier</th></tr></thead><tbody>' +
      rows + "</tbody></table>";
  }

  function renderSection() {
    var sec = S.data.sections || {}, root = el("fantasy-app-root");
    if (!root) return;
    var html;
    switch (S.section) {
      case "streamers": html = tableStreamers(sec.daily_streamers); break;
      case "two_start": html = tableTwoStart(sec.two_start); break;
      case "ros_sp": html = tablePitcher(sec.ros_sp, false); break;
      case "ros_rp": html = tablePitcher(sec.ros_rp, true); break;
      case "ros_hitter": html = tableHitter(sec.ros_hitter); break;
      case "buysell": html = renderBuySell(); break;
      case "closers": html = renderClosers(); break;
      case "callups": html = renderCallups(); break;
      case "dynasty": html = renderDynasty(); break;
      default: html = tableStreamers(sec.daily_streamers);
    }
    root.innerHTML = html;
    // Streamer day pills live inside the freshly rendered section, so their
    // click handlers rebind on every render (same lifecycle as renderSelector).
    root.querySelectorAll(".ff-daypill").forEach(function (b) {
      b.addEventListener("click", function () {
        S.streamerDay = b.getAttribute("data-streamerday");
        renderSection();
      });
    });
    if (window.EEPHUS_GL && EEPHUS_GL.wire) EEPHUS_GL.wire(root);
  }

  // ---- scoring selector + section tabs --------------------------------------
  function renderSelector() {
    var bar = el("fantasy-scoring"); if (!bar) return;
    var cat = (S.data.scoring_catalog) || [{ id: "fgp", label: "FanGraphs Points" }];
    var pts = cat.filter(function (c) { return c.kind !== "roto"; });
    var roto = cat.filter(function (c) { return c.kind === "roto"; });
    function btns(list) {
      return list.map(function (c) {
        return '<button type="button" class="ff-scorebtn' + (c.id === S.system ? " active" : "") + '" data-system="' + c.id + '">' + esc(c.label) + "</button>";
      }).join("");
    }
    bar.innerHTML = '<span class="ff-score-lbl">League scoring</span>' + btns(pts) +
      (roto.length ? '<span class="ff-score-sep">categories</span>' + btns(roto) : "");
    bar.querySelectorAll(".ff-scorebtn").forEach(function (b) {
      b.addEventListener("click", function () {
        S.system = b.getAttribute("data-system");
        renderSelector(); renderSection();
      });
    });
  }
  // The "Dynasty Prospects" tab is injected client-side (the shell's section nav
  // is otherwise static) so it exists before wireTabs() binds click handlers.
  // Idempotent: re-running boot/onData never duplicates the button.
  function injectDynastyTab() {
    var nav = document.querySelector(".mlbstats-sectionnav");
    if (!nav || nav.querySelector('[data-fantasysection="dynasty"]')) return;
    var b = document.createElement("button");
    b.type = "button";
    b.className = "mlbstats-sectionbtn";
    b.setAttribute("data-fantasysection", "dynasty");
    b.setAttribute("role", "tab");
    b.setAttribute("aria-selected", "false");
    b.textContent = "Dynasty Prospects";
    var callups = nav.querySelector('[data-fantasysection="callups"]');
    if (callups && callups.nextSibling) nav.insertBefore(b, callups.nextSibling);
    else nav.appendChild(b);
  }
  function wireTabs() {
    document.querySelectorAll(".mlbstats-sectionbtn[data-fantasysection]").forEach(function (b) {
      b.addEventListener("click", function () {
        document.querySelectorAll(".mlbstats-sectionbtn[data-fantasysection]").forEach(function (x) {
          x.classList.remove("active"); x.setAttribute("aria-selected", "false");
        });
        b.classList.add("active"); b.setAttribute("aria-selected", "true");
        S.section = b.getAttribute("data-fantasysection");
        renderSection();
      });
    });
  }

  // ---- boot / load states ---------------------------------------------------
  function errorState(msg) {
    var root = el("fantasy-app-root");
    if (root) root.innerHTML = '<div class="fantasy-error" role="alert"><strong>Data failed to load.</strong> ' +
      esc(msg || "") + ' The nightly build may be mid-run - <button type="button" id="fantasy-retry" class="ff-scorebtn">retry</button>.</div>';
    var rb = el("fantasy-retry"); if (rb) rb.addEventListener("click", boot);
  }
  function notReady() {
    var root = el("fantasy-app-root");
    if (root) root.innerHTML = '<div class="fantasy-note">Fantasy projections are being computed - check back after the next nightly build.</div>';
  }
  function onData(d) {
    if (!d || !d.players) { notReady(); return; }
    S.data = d;
    S.byId = {}; d.players.forEach(function (p) { S.byId[p.mlbam] = p; });
    var def = (d.scoring_catalog || []).filter(function (c) { return c.default; })[0];
    S.system = def ? def.id : "fgp";
    var banner = el("fantasy-banner");
    if (banner) banner.innerHTML = '<div class="fantasy-asof">' + (d.n_players || 0) + " players · rest-of-season, " +
      Math.round((d.season_fraction || 0) * 100) + "% of " + esc(d.season) + " played · scored in your league format</div>";
    renderSelector(); injectDynastyTab(); wireTabs(); renderSection();
    // Preload the player-links map, then re-render so names upgrade from plain
    // text to merged-card links (matches mlbstats.js / pal.js).
    if (!LINKS && window.EEPHUS_HUB && EEPHUS_HUB.links) {
      EEPHUS_HUB.links().then(function (L) { LINKS = L || null; renderSection(); });
    }
  }
  function boot() {
    fetch(DATA_URL, { cache: "no-cache" }).then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    }).then(onData).catch(function (e) { errorState(String(e && e.message || e)); });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();

  // Minimal module styles (theme-tokened; keeps the shell CSS-file-free).
  var css = document.createElement("style");
  css.textContent = [
    ".fantasy-scoring-bar{display:flex;flex-wrap:wrap;align-items:center;gap:6px;margin:10px 0}",
    ".ff-score-lbl,.ff-score-sep{font:600 11px/1 var(--font-retro,monospace);color:var(--text-tertiary);text-transform:uppercase;letter-spacing:.04em;margin-right:4px}",
    ".ff-score-sep{margin-left:8px}",
    ".ff-scorebtn{font:600 12px/1 var(--font-retro,monospace);padding:6px 11px;border-radius:6px;border:1px solid var(--border-subtle,#3a3a3a);background:var(--bg-secondary);color:var(--text-secondary);cursor:pointer}",
    ".ff-scorebtn.active{background:var(--accent-cyan,#2a7);color:#fff;border-color:transparent}",
    ".fantasy-table{width:100%;border-collapse:collapse;font-size:13px;margin-top:8px}",
    ".fantasy-table th{text-align:right;font:600 11px/1 var(--font-retro,monospace);color:var(--text-tertiary);text-transform:uppercase;letter-spacing:.03em;padding:6px 8px;border-bottom:1px solid var(--border-subtle,#333)}",
    ".fantasy-table td{text-align:right;padding:6px 8px;border-bottom:1px solid var(--border-subtle,#222);color:var(--text-primary)}",
    ".fantasy-table th:nth-child(2),.fantasy-table td.ff-nm{text-align:left}",
    ".fantasy-table td.ff-rk{color:var(--text-tertiary)}",
    ".fantasy-table td.ff-sc{font-weight:700}",
    ".ff-pos{color:var(--accent-green,#3a9)}.ff-neg{color:var(--accent-red,#c55)}",
    ".ff-daypills{display:flex;flex-wrap:wrap;gap:6px;margin:8px 0 2px}",
    ".ff-daypill{font:600 12px/1 var(--font-retro,monospace);padding:6px 11px;border-radius:6px;border:1px solid var(--border-subtle,#3a3a3a);background:var(--bg-secondary);color:var(--text-secondary);cursor:pointer}",
    ".ff-daypill.active{background:var(--accent-cyan,#2a7);color:#fff;border-color:transparent}",
    ".ff-proj{color:var(--text-tertiary);font-style:italic}",
    ".fantasy-note{font-size:12.5px;color:var(--text-secondary);background:var(--bg-secondary);border:1px solid var(--border-subtle,#333);border-radius:8px;padding:9px 12px;margin:8px 0}",
    ".fantasy-cols{display:flex;gap:16px;flex-wrap:wrap}.fantasy-half{flex:1;min-width:280px}",
    ".fantasy-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:10px}",
    ".fantasy-team-card{border:1px solid var(--border-subtle,#333);border-radius:8px;padding:8px 10px;background:var(--bg-secondary)}",
    ".ff-team-hd{font-weight:700;font-size:13px;margin-bottom:5px}",
    ".ff-relief{font-size:12.5px;padding:2px 0}.ff-dim{color:var(--text-tertiary);font-size:11px}",
    ".ff-closer{font:700 9px/1 var(--font-retro,monospace);color:#fff;background:var(--accent-green,#3a9);padding:2px 5px;border-radius:3px}",
    ".ff-hc{font:600 9px/1 var(--font-retro,monospace);color:var(--text-tertiary)}",
    ".fantasy-asof{font-size:12px;color:var(--text-tertiary);margin:4px 0}",
    ".fantasy-error{border:1px solid var(--accent-red,#c55);border-radius:8px;padding:12px;color:var(--text-primary);background:var(--bg-secondary)}",
    ".fantasy-name-link{color:var(--accent-cyan,#2a7);text-decoration:none}.fantasy-name-link:hover{text-decoration:underline}",
    ".ff-tier{font:600 10px/1 var(--font-retro,monospace);color:var(--text-secondary);background:var(--bg-secondary);border:1px solid var(--border-subtle,#333);border-radius:4px;padding:2px 6px;white-space:nowrap}",
    ".ff-tier.ff-tier-elite{color:#fff;background:var(--accent-green,#3a9);border-color:transparent}",
    ".ff-tier.ff-tier-one{color:var(--accent-cyan,#2a7);border-color:var(--accent-cyan,#2a7)}",
    ".ff-mech{font:600 10px/1 var(--font-retro,monospace);border:1px solid var(--border-subtle,#333);border-radius:4px;padding:2px 5px;white-space:nowrap;cursor:help}",
    ".ff-mech.ff-mech-up{color:var(--accent-green,#3a9);border-color:var(--accent-green,#3a9)}",
    ".ff-mech.ff-mech-down{color:var(--accent-red,#c55);border-color:var(--accent-red,#c55)}"
  ].join("");
  document.head.appendChild(css);
})();
