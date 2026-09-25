// Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
// Unauthorized copying of this file, via any medium is strictly prohibited
// Proprietary and confidential
// Written by Noah J. Dengler (@ARKNDJL), 2026
//
// The fantasy player card: one overlay, shared by the fantasy surfaces.
//
// WHAT IT IS. A detail view assembled ENTIRELY from the payload the host page
// already has in memory. There is no per-player page, no new exporter and no
// second fetch of the corpus: the boards download data/fantasy.json once, and
// every card is a lookup into it. The one thing it reaches for is tonight's DFS
// line, and only when the reader opens a card at all (data/dfs.json, fetched
// once per session and cached).
//
// THE ONE eFV BASIS. The dynasty block prints the served `efv` field and
// nothing else. No scale, no quantile, no blend, no arithmetic: rounding to
// nearest is the whole treatment, exactly as assets/dynasty.js does it. This is
// the rule /fantasy/ broke in July when one prospect carried two different
// grades a tab apart, and test_fantasy_split.py greps this file for it.
//
// THE SCORING IS NOT HERE EITHER. The four-format score line comes from the
// HOST through `scoreLine`, because assets/redraft.js already carries the port
// that test_fantasy_split drives against assets/fantasy.js in a JS engine. A
// second copy in this file would be a third implementation nobody is comparing.
(function () {
  "use strict";

  // ---- host binding ---------------------------------------------------------
  // A host is a board client that owns a payload. It hands over accessors
  // rather than data, because the payload arrives after this file runs and the
  // links sidecar arrives later still.
  //
  //   payload()          data/fantasy.json, or null before it lands
  //   links()            the player_links sidecar, or null
  //   scoreLine(rec)     optional: [{label, value, active}] per league format
  //   keeperRound(rank)  optional: the break-even keeper round for a rank
  //   onClose()          optional: the host drops #player= from its own hash
  var HOST = null;
  var S = { id: null, dfs: null, dfsState: "idle", lastFocus: null, node: null,
            hist: { hit: null, pit: null },
            histState: { hit: "idle", pit: "idle" } };
  var DFS_URL = "/data/dfs.json";
  // The season-history boards behind the trend sparkline (2026-08-16). Fetched
  // through the same lazy pattern as the slate: on the first card that needs
  // the side, once per session, cached whatever the outcome. These literals
  // live HERE and not in a board client: test_fantasy_split pins one /data/
  // literal per client, and the card is the one surface that reads history.
  var HIST_URL = { hit: "/data/hitter_history.json", pit: "/data/starter_history.json" };

  function attach(host) {
    HOST = host || null;
    ensureStyles();
  }
  function payload() { return (HOST && HOST.payload && HOST.payload()) || null; }
  function links() { return (HOST && HOST.links && HOST.links()) || null; }

  // ---- helpers --------------------------------------------------------------
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }
  function num(v, d) { return (v == null || isNaN(v)) ? "-" : Number(v).toFixed(d == null ? 1 : d); }
  function teamLogo(team) {
    return (window.EEPHUS_HUB && EEPHUS_HUB.teamLogo && team) ? EEPHUS_HUB.teamLogo(team) : "";
  }
  // Glossary spans. Every slug below is checked against data/glossary.json
  // before it is used: a [data-gl] carrying a slug the artifact does not have
  // renders a term that looks interactive and defines nothing.
  function gl(label, slug) {
    return '<span class="g-term" data-gl="' + esc(slug) + '">' + esc(label) + "</span>";
  }
  function chip(label, value, cls) {
    if (value == null || value === "") return "";
    return '<span class="fc-chip' + (cls ? " " + cls : "") + '"><b>' + label + "</b>" +
      value + "</span>";
  }
  // Local calendar day, built from date PARTS. A bare ISO string through
  // new Date() is parsed as UTC and reads as the previous day west of
  // Greenwich, which would label tonight's slate as yesterday's every evening.
  function todayLocal() {
    var t = new Date();
    return t.getFullYear() + "-" + ("0" + (t.getMonth() + 1)).slice(-2) +
      "-" + ("0" + t.getDate()).slice(-2);
  }
  function dayLabel(d) {
    var p = String(d || "").split("-");
    if (p.length !== 3) return esc(d);
    var dt = new Date(+p[0], +p[1] - 1, +p[2]);
    return ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"][dt.getDay()] +
      " " + (+p[1]) + "/" + (+p[2]);
  }

  // ---- lookups over the served payload --------------------------------------
  // Keyed by mlbam AND side, the same composite the boards use: a two-way
  // player has TWO records and keying on mlbam alone is last-write-wins.
  function recsFor(mlbam) {
    var d = payload(), out = [];
    if (!d || !d.players) return out;
    var want = String(mlbam);
    d.players.forEach(function (p) { if (String(p.mlbam) === want) out.push(p); });
    // Hitter first when a player carries both, because that is the row a reader
    // who clicked a name on a hitter board is looking for.
    out.sort(function (a, b) { return (a.side === "hit" ? 0 : 1) - (b.side === "hit" ? 0 : 1); });
    return out;
  }
  function sections() { var d = payload(); return (d && d.sections) || {}; }
  function inList(list, mlbam) {
    var want = String(mlbam), hit = false;
    (list || []).forEach(function (e) {
      var id = (e && typeof e === "object") ? e.mlbam : e;
      if (String(id) === want) hit = true;
    });
    return hit;
  }
  function dynastyRow(mlbam) {
    var want = String(mlbam), out = null;
    (sections().dynasty || []).forEach(function (d) { if (String(d.mlbam) === want) out = d; });
    return out;
  }
  function callupRow(mlbam) {
    var want = String(mlbam), out = null;
    (sections().callup_watch || []).forEach(function (c) { if (String(c.mlbam) === want) out = c; });
    return out;
  }
  // Bullpen pecking order. closer_depth is {org: [mlbam, ...]} in leverage
  // order, so the INDEX is the role and the array is the depth chart.
  function bullpenRole(mlbam) {
    var depth = sections().closer_depth || {}, want = String(mlbam), out = null;
    Object.keys(depth).forEach(function (tm) {
      (depth[tm] || []).forEach(function (m, i) {
        if (String(m) === want && !out) out = { team: tm, idx: i, n: (depth[tm] || []).length };
      });
    });
    return out;
  }
  // Announced probables first, projected second-starts after, one row per date.
  function startsFor(mlbam) {
    var want = String(mlbam), by = {};
    (sections().daily_streamers || []).forEach(function (st) {
      if (String(st.mlbam) !== want) return;
      by[st.date || ""] = { date: st.date, opp: st.opp_org, venue: st.venue,
                            home: st.is_home, pts: st.per_start_fgp, projected: false };
    });
    (sections().two_start || []).forEach(function (t) {
      if (String(t.mlbam) !== want) return;
      (t.legs || []).forEach(function (l) {
        if (by[l.date || ""]) return;
        by[l.date || ""] = { date: l.date, opp: l.opp_org, home: l.is_home,
                             pts: l.exp_fgp, projected: !!l.projected };
      });
    });
    return Object.keys(by).sort().map(function (k) { return by[k]; });
  }
  function fullCardHref(mlbam) {
    var L = links();
    var e = L && L.byMlbam && L.byMlbam[String(mlbam)];
    return (e && e.key) ? ("/projections/#player=" + e.key) : null;
  }

  // ---- the lazy sidecars (tonight's slate + the season history) -------------
  // Each is fetched once per session, on the first card that needs it, and
  // cached whatever the outcome. ONE fetch call site serves both, so the
  // source contract in test_fantasy_split stays a one-line pin. A slate we
  // could not get is a NOTE on its block, not a silent omission: a reader who
  // knows the player is on tonight's slate and sees nothing here would read
  // that as "not playing". A history we could not get simply renders no trend,
  // because a missing sparkline claims nothing.
  // Content stamps: the slate and BOTH history boards are build-time
  // artifacts, so the /fantasy/ shell emits window.EEPHUS_DATA_VERS entries
  // for all three and the reads ride content-versioned URLs under DEFAULT
  // caching. The histories are the two heaviest lazy payloads this overlay
  // owns, which is exactly the transfer the stamp exists to save. No stamp
  // (hand-served page, missing emission) keeps the no-cache revalidation
  // below unchanged. Betting payloads never enter the map: the close job
  // mutates them intra-day with no rebuild.
  function stampedURL(url) {
    try {
      var vers = (typeof window !== "undefined" && window.EEPHUS_DATA_VERS) || null;
      var v = vers && vers[url.split("/").pop()];
      return v ? url + "?v=" + encodeURIComponent(v) : null;
    } catch (e) { return null; }
  }
  function getJson(url, ok, bad) {
    var stamped = stampedURL(url);
    var opts = stamped ? undefined : { cache: "no-cache" };
    if (stamped) url = stamped;
    fetch(url, opts).then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    }).then(ok).catch(bad);
  }
  function loadDfs(then) {
    if (S.dfsState === "done" || S.dfsState === "failed") { then(); return; }
    if (S.dfsState === "loading") return;
    S.dfsState = "loading";
    getJson(DFS_URL, function (d) {
      S.dfs = d || null; S.dfsState = "done"; then();
    }, function () {
      S.dfs = null; S.dfsState = "failed"; then();
    });
  }
  function loadHist(side, then) {
    var st = S.histState[side];
    if (st === "done" || st === "failed") { then(); return; }
    if (st === "loading") return;
    S.histState[side] = "loading";
    getJson(HIST_URL[side], function (d) {
      S.hist[side] = d || null; S.histState[side] = "done"; then();
    }, function () {
      S.hist[side] = null; S.histState[side] = "failed"; then();
    });
  }
  // {points: [{s: season, v: index}], asof} for a player, or null. The
  // artifacts are the PER-SEASON qualified boards (history[year].hitters /
  // .starters), so the series is one point per qualified season; most of the
  // pool never qualified and gets no block, which is the honest absence.
  function histSeriesFor(side, mlbam) {
    var d = S.hist[side];
    var h = d && d.history;
    if (!h || typeof h !== "object") return null;
    var listKey = side === "hit" ? "hitters" : "starters";
    var valKey = side === "hit" ? "hem_plus" : "sem_plus";
    var want = String(mlbam), pts = [];
    Object.keys(h).sort().forEach(function (y) {
      var rows = (h[y] || {})[listKey] || [];
      for (var i = 0; i < rows.length; i++) {
        if (String(rows[i].mlbam) === want && rows[i][valKey] != null) {
          pts.push({ s: y, v: Number(rows[i][valKey]) });
          return;
        }
      }
    });
    if (pts.length < 2) return null;
    return { points: pts, asof: d.generated_at || null };
  }
  function dfsRowsFor(mlbam) {
    var d = S.dfs, want = String(mlbam), out = [];
    // slate_date is what makes a payload a SLATE. Without it this is some other
    // JSON that happens to have a players array, and pricing a card off it
    // would be worse than showing no tonight block at all.
    if (!d || !d.slate_date || !d.players) return out;
    d.players.forEach(function (p) { if (String(p.mlbam) === want) out.push(p); });
    return out;
  }

  // ---- blocks ---------------------------------------------------------------
  function head(mlbam, recs) {
    var p = recs[0] || {};
    var elig = {};
    recs.forEach(function (r) { (r.elig || []).forEach(function (e) { elig[e] = 1; }); });
    var chips = Object.keys(elig).map(function (e) {
      return '<span class="fc-elig">' + esc(e) + "</span>";
    }).join("");
    var href = fullCardHref(mlbam);
    // The roster flag (fantasy_export roster_status, FLAGGED, NEVER FILTERED):
    // the tooltip is the payload's own basis string.
    var off = recs.some(function (r) { return r && r.roster_status === "off_roster"; });
    var basis = ((payload() || {}).roster_status || {}).basis || "Off the active roster at build time.";
    return '<div class="fc-head">' +
      '<h2 id="fc-title" class="fc-name">' + teamLogo(p.team) + " " + esc(p.name || "Player") + "</h2>" +
      '<div class="fc-sub">' + esc(p.team || "") + (p.pos ? " &middot; " + esc(p.pos) : "") +
      (recs.length > 1 ? ' <span class="fc-elig fc-twoway">two-way</span>' : "") +
      (off ? ' <span class="fc-elig fc-off" title="' + esc(basis) + '">off roster</span>' : "") +
      " " + chips + "</div>" +
      (href
        ? '<a class="fc-out" href="' + esc(href) + '">Full MLB card</a>'
        : '<span class="fc-out fc-out-off" title="No merged MLB card in player_links yet.">No MLB card yet</span>') +
      "</div>";
  }
  function scoreBlock(rec) {
    if (!HOST || typeof HOST.scoreLine !== "function") return "";
    var rows = HOST.scoreLine(rec) || [];
    if (!rows.length) return "";
    // Next season's full-season line once the regular season is over
    // (fantasy_export.season_mode); the rest of this season otherwise.
    var d = payload() || {};
    var span = d.mode === "next_season" ? (d.target_season + " full season") : "Rest of season";
    return '<div class="fc-sec"><div class="fc-sec-h">' + esc(span) + ", by league format</div>" +
      '<div class="fc-scores">' + rows.map(function (r) {
        return '<span class="fc-score' + (r.active ? " is-active" : "") + '">' +
          '<span class="fc-score-l">' + esc(r.label) + "</span>" +
          '<span class="fc-score-v">' + esc(r.value) + "</span></span>";
      }).join("") + "</div>" +
      '<div class="fc-fine">Points: projection times the format\'s weight table. Categories: summed ' +
      "z-scores over his board, a position in a pool, not a total.</div></div>";
  }
  var HIT_TAPE = [["pa", "PA", 0], ["hr", "HR", 0], ["r", "R", 0], ["rbi", "RBI", 0],
                  ["sb", "SB", 0], ["avg", "AVG", 3], ["obp", "OBP", 3], ["slg", "SLG", 3]];
  var SP_TAPE = [["ip", "IP", 1], ["k", "K", 0], ["era", "ERA", 2], ["whip", "WHIP", 2],
                 ["qs", "QS", 0], ["w", "W", 0], ["gs", "GS", 0]];
  var RP_TAPE = [["ip", "IP", 1], ["k", "K", 0], ["era", "ERA", 2], ["whip", "WHIP", 2],
                 ["sv", "SV", 0], ["hld", "HLD", 0]];
  function tapeBlock(rec) {
    var ros = rec.ros || {};
    var cols = rec.side === "hit" ? HIT_TAPE : (ros.role === "RP" ? RP_TAPE : SP_TAPE);
    // `_est` is the exporter naming its own display-layer legs. Carrying that
    // mark through is cheaper than a footnote and more honest than dropping it.
    var est = {};
    (ros._est || []).forEach(function (k) { est[k] = 1; });
    var cells = cols.map(function (c) {
      if (ros[c[0]] == null) return "";
      return '<span class="fc-stat' + (est[c[0]] ? " is-est" : "") + '">' +
        '<span class="fc-stat-l">' + c[1] + "</span>" + num(ros[c[0]], c[2]) + "</span>";
    }).join("");
    if (!cells) return "";
    var anyEst = cols.some(function (c) { return est[c[0]] && ros[c[0]] != null; });
    return '<div class="fc-sec"><div class="fc-sec-h">Projected line, ' +
      (rec.side === "hit" ? "hitting" : "pitching") + "</div>" +
      '<div class="fc-tape">' + cells + "</div>" +
      (anyEst
        ? '<div class="fc-fine">Dotted underline: an estimated leg, not a direct projection.</div>'
        : "") + "</div>";
  }
  function skillBlock(rec) {
    var sk = rec.skill || {}, out = [];
    if (rec.side === "hit" && sk.hem_plus != null) out.push(chip(gl("HEM+", "hem_plus"), num(sk.hem_plus, 0)));
    if (rec.side === "pit" && sk.sem_plus != null) out.push(chip(gl("SEM+", "sem_plus"), num(sk.sem_plus, 0)));
    if (rec.side === "pit" && sk.rem_plus != null) out.push(chip(gl("REM+", "rem_plus"), num(sk.rem_plus, 0)));
    if (sk.gmli != null) out.push(chip(gl("gmLI", "gmli"), num(sk.gmli, 2)));
    // ONE UNIT, TWO ARITHMETICS. Hitter luck_gap is xwOBA minus wOBA and
    // pitcher luck is wOBA minus xwOBA allowed, both in wOBA points and both
    // + when results sit behind the expected stats. (The hitter side was
    // xHEM+ minus HEM+ in plus-stat points until 2026-09-24.)
    var luck = rec.side === "hit" ? sk.luck_gap : sk.luck;
    if (luck != null) {
      out.push(chip(gl("xwOBA", "xwoba") + " gap", (luck > 0 ? "+" : "") + num(luck, 3),
                    luck > 0 ? "fc-good" : "fc-bad"));
    }
    if (inList(sections().buy_low, rec.mlbam)) out.push(chip("Signal", "buy low", "fc-good"));
    if (inList(sections().sell_high, rec.mlbam)) out.push(chip("Signal", "sell high", "fc-bad"));
    var mt = rec.swing_trend;
    if (mt && mt.delta != null) {
      out.push(chip(gl("Swing+", "swing_plus") + " trend",
                    (mt.delta > 0 ? "+" : "") + num(mt.delta, 0),
                    mt.delta > 0 ? "fc-good" : "fc-bad"));
    }
    out = out.filter(Boolean);
    if (!out.length) return "";
    return '<div class="fc-sec"><div class="fc-sec-h">Skill and luck</div>' +
      '<div class="fc-chips">' + out.join("") + "</div>" +
      '<div class="fc-fine">Positive gap: results behind the expected stats. Descriptive, not in the ' +
      "projection. Whether a gap closes or persists is unmeasured.</div></div>";
  }
  function startsBlock(rec) {
    if (rec.side !== "pit") return "";
    var list = startsFor(rec.mlbam);
    if (!list.length) return "";
    return '<div class="fc-sec"><div class="fc-sec-h">Upcoming starts</div>' +
      '<div class="fc-rows">' + list.map(function (s) {
        return '<div class="fc-row"><span>' + esc(dayLabel(s.date)) + "</span>" +
          "<span>" + (s.home === true ? "vs " : (s.home === false ? "@ " : "")) +
          esc(s.opp || "") + (s.venue ? " &middot; " + esc(s.venue) : "") +
          (s.projected ? ' <span class="fc-dim">(projected)</span>' : "") + "</span>" +
          "<span>" + num(s.pts, 1) + " pts</span></div>";
      }).join("") + "</div>" +
      '<div class="fc-fine">Projected: team schedule on normal rest, not announced.</div></div>';
  }
  function roleBlock(rec) {
    if (rec.side !== "pit") return "";
    var r = bullpenRole(rec.mlbam);
    if (!r) return "";
    // Role ORDER, never a likelihood (closer gate RED 2026-08-16).
    var role = r.idx === 0 ? "closer slot" : (r.idx === 1 ? "next in line" : "bullpen depth");
    return '<div class="fc-sec"><div class="fc-sec-h">' + gl("Bullpen role", "reliever_roles") + "</div>" +
      '<div class="fc-chips">' + chip(esc(r.team), role, r.idx === 0 ? "fc-good" : "") +
      chip("Depth chart", "#" + (r.idx + 1) + " of " + r.n) + "</div>" +
      '<div class="fc-fine">Order by a gmLI-led score with saves and REM+, over the reliever ' +
      "board's qualified arms. Not a saves projection.</div></div>";
  }
  // ---- the season-trend sparkline (2026-08-16) ------------------------------
  // The cards.js precedent: inline SVG, theme tokens only, no canvas and no
  // library. Strokes ride var() through a style attribute because presentation
  // ATTRIBUTES cannot carry var() but the CSS property can. One point per
  // qualified season; the plan asked for a monthly series, but no committed
  // artifact carries one (hitter_history/starter_history are yearly boards),
  // and this card does not invent data it does not have.
  function sparkSvg(pts) {
    var W = 220, H = 44, pad = 4;
    var vals = pts.map(function (p) { return p.v; });
    var lo = Math.min.apply(null, vals), hi = Math.max.apply(null, vals);
    if (hi <= lo) hi = lo + 1;
    var up = vals[vals.length - 1] >= vals[0];
    var tone = "var(--accent-" + (up ? "green" : "red") + ")";
    var d = pts.map(function (p, i) {
      var x = pad + (i / (pts.length - 1)) * (W - pad * 2);
      var y = H - pad - ((p.v - lo) / (hi - lo)) * (H - pad * 2);
      return (i ? "L" : "M") + x.toFixed(1) + " " + y.toFixed(1);
    }).join(" ");
    var lastY = H - pad - ((vals[vals.length - 1] - lo) / (hi - lo)) * (H - pad * 2);
    return '<svg class="fc-spark" viewBox="0 0 ' + W + " " + H + '" width="' + W + '" height="' + H +
      '" role="img" aria-label="season index trend, ' + pts.length + ' seasons">' +
      '<path d="' + d + '" fill="none" style="stroke:' + tone + ';stroke-width:1.5"/>' +
      '<circle cx="' + (W - pad).toFixed(1) + '" cy="' + lastY.toFixed(1) +
      '" r="2" style="fill:' + tone + '"/></svg>';
  }
  function histBlock(rec) {
    var side = rec.side === "hit" ? "hit" : "pit";
    var label = side === "hit" ? "HEM+" : "SEM+";
    var term = side === "hit" ? "hem_plus" : "sem_plus";
    if (S.histState[side] === "loading") {
      return '<div class="fc-sec"><div class="fc-sec-h">' + gl(label, term) + " trend</div>" +
        '<div class="fc-fine">Loading the season history.</div></div>';
    }
    var series = histSeriesFor(side, rec.mlbam);
    if (!series) return "";
    var pts = series.points;
    var first = pts[0], last = pts[pts.length - 1];
    return '<div class="fc-sec"><div class="fc-sec-h">' + gl(label, term) + " trend</div>" +
      '<div class="fc-sparkrow">' + sparkSvg(pts) +
      '<span class="fc-spark-range">' + esc(first.s) + " " + num(first.v, 0) +
      ' <span class="fc-dim">to</span> ' + esc(last.s) + " " + num(last.v, 0) + "</span></div>" +
      '<div class="fc-fine">One point per qualified season' +
      (series.asof ? ", as of " + esc(series.asof) : "") + ". Unqualified seasons are skipped.</div></div>";
  }

  // ---- the next-7 schedule strip (2026-08-16) -------------------------------
  // sections.team_next7 is baked by fantasy_export off the same 7-day slate the
  // two-start board rides. Chips color by opponent Offense+: 105 or tougher
  // reads hard, 95 or softer reads soft, anything else (a missing measurement
  // included) stays neutral, which is the same "missing is not average" rule
  // the DFS matchup mark enforces.
  function next7Block(recs) {
    var team = (recs[0] || {}).team;
    if (!team) return "";
    var sched = (sections().team_next7 || {})[team];
    if (!sched || !sched.length) return "";
    var chips = sched.map(function (g) {
      var cls = "";
      if (g.opp_off != null) {
        if (g.opp_off >= 105) cls = " fc-bad";
        else if (g.opp_off <= 95) cls = " fc-good";
      }
      var title = (g.home ? "vs " : "@ ") + (g.opp || "?") +
        (g.opp_off != null ? ". Opponent Offense+ " + g.opp_off : ". Opponent offense unmeasured") +
        (g.opp_bp != null ? ", Bullpen+ " + g.opp_bp : "") + ".";
      return '<span class="fc-chip fc-n7' + cls + '" title="' + esc(title) + '"><b>' +
        esc(dayLabel(g.d)) + "</b>" + esc((g.home ? "vs " : "@ ") + (g.opp || "?")) +
        (g.opp_off != null ? '<span class="fc-n7-off">Off+ ' + esc(g.opp_off) + "</span>" : "") +
        "</span>";
    }).join("");
    return '<div class="fc-sec"><div class="fc-sec-h">' + esc(team) + ", next 7 days</div>" +
      '<div class="fc-chips">' + chips + "</div>" +
      '<div class="fc-fine">Border by opponent ' + gl("Offense+", "offense_plus") +
      ": 105 or higher red, 95 or lower green, unmeasured neutral.</div></div>";
  }

  function dynastyBlock(mlbam) {
    var d = dynastyRow(mlbam), cw = callupRow(mlbam);
    if (!d && !cw) return "";
    var out = "";
    if (d) {
      var band = d.band || [];
      // SERVED VERBATIM. Math.round is display rounding to nearest, which is
      // the house convention for eFV; nothing else touches the grade.
      out += '<div class="fc-chips">' +
        chip("Rank", "#" + esc(d.rank)) +
        chip(gl("eFV", "xfv"), d.efv == null ? "-" : String(Math.round(d.efv))) +
        chip("Tier", esc(d.tier || "-")) +
        chip(gl("ETA", "eta"), esc(d.eta || "-")) +
        chip(gl("Star", "star_odds"), d.star == null ? null : num(d.star, 0) + "%", "fc-good") +
        chip(gl("Bust", "bust_prob"), d.bust == null ? null : num(d.bust, 0) + "%", "fc-bad") +
        chip(gl("Surplus", "surplus_value"), d.surplus == null ? null : "$" + num(d.surplus, 0) + "M") +
        chip("Outlook", (band[0] != null && band[1] != null)
          ? ("$" + num(band[0], 0) + "-" + num(band[1], 0) + "M") : null) +
        (HOST && typeof HOST.keeperRound === "function"
          ? chip("Keep by (farm draft)", "R" + HOST.keeperRound(d.rank)) : "") +
        "</div>";
    }
    if (cw) {
      out += '<div class="fc-fine">On Call-up Watch, ETA ' + esc(cw.eta || "-") + ".</div>";
    }
    out += '<div class="fc-fine">eFV is the served board grade, same as PROSPX. The rank is a display ' +
      "blend over it, not a separate model.</div>";
    return '<div class="fc-sec"><div class="fc-sec-h">Dynasty</div>' + out + "</div>";
  }
  // The two links out of this block are the module hash, not /dfs/. That dir is
  // a redirect stub since the 2026-08-07 merge, so a page-absolute href would
  // send a reader who is ALREADY on /fantasy/ out and straight back in. The
  // coordinator resolves the namespaced form in place.
  function dfsBlock(mlbam) {
    if (S.dfsState === "loading") {
      return '<div class="fc-sec"><div class="fc-sec-h">Tonight</div>' +
        '<div class="fc-fine">Checking tonight\'s slate.</div></div>';
    }
    if (S.dfsState === "failed") {
      return '<div class="fc-sec"><div class="fc-sec-h">Tonight</div>' +
        '<div class="fc-fine">The daily slate did not load. Board: ' +
        '<a class="fc-link" href="#m=dfs&amp;section=slate">DFS</a>.</div></div>';
    }
    var rows = dfsRowsFor(mlbam);
    if (!rows.length) return "";
    var d = S.dfs || {};
    var stale = d.stale_slate || (d.slate_date && String(d.slate_date) < todayLocal());
    var cat = d.scoring_catalog || [];
    var body = rows.map(function (p) {
      var pts = cat.map(function (c) {
        var v = (p.pts || {})[c.id];
        return v == null ? "" : chip(esc(c.label), num(v, 1));
      }).join("");
      return '<div class="fc-chips">' +
        chip("Game", esc((p.is_home ? "vs " : "@ ") + (p.opp || ""))) +
        ((p.ctx || {}).opp_sp ? chip("Opp SP", esc(p.ctx.opp_sp)) : "") +
        (p.start_rate == null ? "" : chip("Start odds", Math.round(p.start_rate * 100) + "%")) +
        pts + "</div>";
    }).join("");
    return '<div class="fc-sec"><div class="fc-sec-h">' +
      (stale ? "On the " + esc(d.slate_date || "last") + " slate" : "Tonight") + "</div>" + body +
      '<div class="fc-fine">' +
      (stale
        ? "Not today's slate: these numbers are from " + esc(d.slate_date || "an earlier day") + ". "
        : "") +
      'Per-game contest projections. Full board and optimizer: ' +
      '<a class="fc-link" href="#m=dfs&amp;section=slate">DFS</a>.</div></div>';
  }

  // ---- render ---------------------------------------------------------------
  function bodyHtml(mlbam) {
    var recs = recsFor(mlbam);
    var dyn = dynastyBlock(mlbam);
    if (!recs.length) {
      // A prospect on the dynasty board carries no rest-of-season record, which
      // is not an error: he has not played in the majors. Say which it is.
      if (dyn) return head(mlbam, [dynastyIdentity(mlbam)]) + dyn;
      // A Closer Grid arm comes from the reliever board, not the projection
      // pool, so he can have a bullpen role and no projection. Name him and
      // show the role rather than a blank card.
      var cr = (sections().closer_rows || {})[String(mlbam)];
      if (cr) {
        return head(mlbam, [{ name: cr.name, team: cr.team, pos: "RP", elig: [] }]) +
          roleBlock({ side: "pit", mlbam: mlbam }) +
          '<div class="fc-sec"><div class="fc-fine">No projection in the current build.</div></div>';
      }
      return head(mlbam, [{}]) +
        '<div class="fc-sec"><div class="fc-fine">Not in the current build.</div></div>';
    }
    var out = head(mlbam, recs);
    recs.forEach(function (rec) {
      out += scoreBlock(rec) + tapeBlock(rec) + skillBlock(rec) + histBlock(rec) +
        startsBlock(rec) + roleBlock(rec);
    });
    return out + next7Block(recs) + dyn + dfsBlock(mlbam);
  }
  // A dynasty-only row is enough to name a player, so the head is built from it
  // rather than rendering a card with a blank name.
  function dynastyIdentity(mlbam) {
    var d = dynastyRow(mlbam) || callupRow(mlbam) || {};
    return { name: d.name, team: d.org, pos: d.pos, elig: [] };
  }

  // THE WHOLE OVERLAY IS ONE innerHTML WRITE, panel and backdrop together. It
  // could keep a stable body node and write into that, but then every paint
  // depends on a querySelector against a subtree this module does not own, and
  // one null return is a thrown TypeError inside a hashchange handler. Rebuild,
  // rebind, done.
  function shell() {
    if (S.node) return S.node;
    var n = document.createElement("div");
    n.className = "fc-wrap";
    n.setAttribute("hidden", "hidden");
    document.body.appendChild(n);
    S.node = n;
    return n;
  }
  function paint() {
    if (S.id == null) return;
    var n = shell();
    n.innerHTML = '<div class="fc-back" data-fcclose="1"></div>' +
      '<div class="fc-panel" role="dialog" aria-modal="true" aria-labelledby="fc-title">' +
      '<button type="button" class="fc-x" data-fcclose="1" aria-label="Close player card">Close</button>' +
      '<div class="fc-body">' + bodyHtml(S.id) + "</div></div>";
    var shut = n.querySelectorAll ? n.querySelectorAll("[data-fcclose]") : null;
    if (shut && shut.forEach) {
      shut.forEach(function (b) { b.addEventListener("click", function () { close(); }); });
    }
    if (window.EEPHUS_GL && EEPHUS_GL.wire) EEPHUS_GL.wire(n);
  }
  function open(mlbam) {
    if (mlbam == null || !payload()) return;
    S.id = String(mlbam);
    var n = shell();
    n.removeAttribute("hidden");
    try { S.lastFocus = document.activeElement; } catch (e) { S.lastFocus = null; }
    paint();
    focusCard();
    // The lazy legs. Each is fetched on the first card of the session that
    // needs it, then cached, so the second card costs nothing and a reader who
    // never opens one never downloads the slate or the history at all. A
    // repaint REPLACES the panel, so focus is taken back deliberately instead
    // of being dropped on the document.
    function repaint() { if (S.id == null) return; paint(); focusCard(); }
    loadDfs(repaint);
    recsFor(mlbam).forEach(function (rec) {
      loadHist(rec.side === "hit" ? "hit" : "pit", repaint);
    });
  }
  function focusCard() {
    var n = S.node;
    var x = (n && n.querySelector) ? n.querySelector(".fc-x") : null;
    if (x && x.focus) x.focus();
  }
  function close() {
    if (S.id == null) return;
    S.id = null;
    if (S.node) S.node.setAttribute("hidden", "hidden");
    if (HOST && typeof HOST.onClose === "function") HOST.onClose();
    if (S.lastFocus && S.lastFocus.focus) { try { S.lastFocus.focus(); } catch (e) { /* gone */ } }
    S.lastFocus = null;
  }
  // The card follows the hash, so the host calls this on every route read and
  // the card decides whether that is an open, a close or a no-op.
  function sync(mlbam) {
    if (mlbam == null || mlbam === "") { close(); return; }
    if (String(mlbam) === S.id) { paint(); return; }
    open(mlbam);
  }
  function isOpen() { return S.id != null; }

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && S.id != null) close();
  });

  // ---- styles (theme tokens only) -------------------------------------------
  var STYLED = false;
  function ensureStyles() {
    if (STYLED) return;
    STYLED = true;
    var css = document.createElement("style");
    css.textContent = [
      ".fc-wrap[hidden]{display:none}",
      // z-index 60 is deliberate: above every piece of page chrome (site.css
      // tops out at 50) and BELOW the site's own overlays, which start at 4000.
      // The glossary popover is one of those, and a term inside this card has
      // to be able to open over it.
      ".fc-wrap{position:fixed;inset:0;z-index:60;display:flex;align-items:flex-start;justify-content:center;padding:24px 12px;overflow:auto}",
      ".fc-back{position:fixed;inset:0;background:var(--bg-primary);opacity:.86}",
      ".fc-panel{position:relative;width:100%;max-width:720px;background:var(--bg-secondary);border:1px solid var(--border);padding:16px 18px 20px}",
      ".fc-x{position:absolute;top:10px;right:10px;font:600 11px/1 var(--font-retro,monospace);padding:6px 10px;border:1px solid var(--border);background:var(--bg-primary);color:var(--text-secondary);cursor:pointer;text-transform:uppercase;letter-spacing:.04em}",
      ".fc-head{padding-right:70px;border-bottom:1px solid var(--border);padding-bottom:10px;margin-bottom:4px}",
      ".fc-name{font-size:20px;line-height:1.2;margin:0;color:var(--text-primary)}",
      ".fc-sub{font-size:12.5px;color:var(--text-secondary);margin-top:3px;display:flex;flex-wrap:wrap;gap:5px;align-items:center}",
      ".fc-elig{font:600 10px/1 var(--font-retro,monospace);color:var(--text-tertiary);border:1px solid var(--border);padding:2px 5px}",
      ".fc-twoway{color:var(--accent-cyan);border-color:var(--accent-cyan)}",
      ".fc-off{color:var(--accent-red);border-color:var(--accent-red);cursor:help}",
      ".fc-out{display:inline-block;margin-top:8px;font:600 11px/1 var(--font-retro,monospace);color:var(--accent-cyan);text-decoration:none;border:1px solid var(--accent-cyan);padding:6px 10px}",
      ".fc-out:hover{text-decoration:underline}",
      ".fc-out-off{color:var(--text-tertiary);border-color:var(--border);cursor:help}",
      ".fc-sec{margin-top:14px}",
      ".fc-sec-h{font:600 11px/1 var(--font-retro,monospace);color:var(--text-tertiary);text-transform:uppercase;letter-spacing:.04em;margin-bottom:6px}",
      ".fc-scores{display:flex;flex-wrap:wrap;gap:8px}",
      ".fc-score{display:inline-flex;flex-direction:column;gap:2px;border:1px solid var(--border);padding:5px 9px;min-width:88px}",
      ".fc-score.is-active{border-color:var(--accent-cyan)}",
      ".fc-score-l{font:600 9px/1 var(--font-retro,monospace);color:var(--text-tertiary);text-transform:uppercase;letter-spacing:.04em}",
      ".fc-score-v{font:700 15px/1 var(--font-retro,monospace);color:var(--text-primary)}",
      ".fc-tape{display:flex;flex-wrap:wrap;gap:6px 14px}",
      ".fc-stat{display:inline-flex;flex-direction:column;gap:2px;font:700 13px/1 var(--font-retro,monospace);color:var(--text-primary)}",
      ".fc-stat.is-est{border-bottom:1px dotted var(--text-tertiary)}",
      ".fc-stat-l{font:600 9px/1 var(--font-retro,monospace);color:var(--text-tertiary);text-transform:uppercase;letter-spacing:.04em}",
      ".fc-chips{display:flex;flex-wrap:wrap;gap:6px}",
      ".fc-chip{font:600 11px/1.3 var(--font-retro,monospace);border:1px solid var(--border);padding:4px 7px;color:var(--text-primary);white-space:nowrap}",
      ".fc-chip b{display:block;font:600 9px/1 var(--font-retro,monospace);color:var(--text-tertiary);text-transform:uppercase;letter-spacing:.04em;margin-bottom:2px}",
      ".fc-chip.fc-good{border-color:var(--accent-green)}",
      ".fc-chip.fc-bad{border-color:var(--accent-red)}",
      ".fc-n7{display:inline-flex;flex-direction:column;gap:2px}",
      ".fc-n7-off{font:600 9px/1 var(--font-retro,monospace);color:var(--text-tertiary);margin-top:2px}",
      ".fc-sparkrow{display:flex;align-items:center;gap:10px;flex-wrap:wrap}",
      ".fc-spark{max-width:100%;height:auto}",
      ".fc-spark-range{font:600 11px/1.3 var(--font-retro,monospace);color:var(--text-secondary);white-space:nowrap}",
      ".fc-rows{display:flex;flex-direction:column;gap:3px}",
      ".fc-row{display:flex;justify-content:space-between;gap:10px;font-size:12.5px;color:var(--text-primary);border-bottom:1px solid var(--border-light);padding:3px 0}",
      ".fc-dim{color:var(--text-tertiary)}",
      ".fc-fine{font-size:11.5px;color:var(--text-tertiary);margin-top:6px;line-height:1.45}",
      ".fc-link{color:var(--accent-cyan);text-decoration:none}.fc-link:hover{text-decoration:underline}",
      "@media (max-width:640px){.fc-wrap{padding:0}.fc-panel{max-width:none;min-height:100%;border:0}}"
    ].join("");
    document.head.appendChild(css);
  }

  window.EEPHUS_FANTASY_CARD = { attach: attach, open: open, close: close,
                                 sync: sync, isOpen: isOpen };
})();
