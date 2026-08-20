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
//
// The four LEADERBOARD surfaces (ROS Hitters / ROS SP / ROS RP / Dynasty) render
// as PROSPX-pattern cards; the four small surfaces stay tables. See the block
// comment above the column maps for the row counts behind each call.
(function () {
  "use strict";
  var DATA_URL = "/data/fantasy.json";
  // streamerDay0 is the first slate tableStreamers actually served this load. It
  // is not user state; it exists so writeHash can tell "the user picked a day"
  // from "the day the board opened on" and keep the default out of the URL.
  var S = { data: null, system: "fgp", section: "streamers", byId: {}, streamerDay: null, streamerDay0: null };
  // Sort state, one entry per CARD board (the table surfaces keep their served
  // order). Every board defaults to what it showed before the card conversion,
  // so the first paint is identical in ordering to the retired tables.
  var SORT = {
    ros_hitter: { key: "score", asc: false },
    ros_sp: { key: "score", asc: false },
    ros_rp: { key: "score", asc: false },
    dynasty: { key: "rank", asc: true }
  };
  // Copied off SORT above, before anything can mutate it, so writeHash can omit
  // a board still sitting on its served default. Deriving it instead of writing
  // a second literal is the point: two literals would drift the first time a
  // board's default changed and the URL would start carrying a phantom sort.
  var SORT_DEFAULTS = {};
  Object.keys(SORT).forEach(function (k) { SORT_DEFAULTS[k] = { key: SORT[k].key, asc: SORT[k].asc }; });
  // Resolve a section entry to its player record. Section lists are bare mlbam
  // ids and every section except buy/sell is single-sided, so the SIDE comes from
  // the calling surface. buy/sell entries carry their own side (see
  // fantasy_export._buy_sell); the object form is handled by recOf below.
  function rec(mlbam, side) { return S.byId[mlbam + "|" + side]; }
  function recOf(entry, fallbackSide) {
    if (entry && typeof entry === "object") return rec(entry.mlbam, entry.side);
    // Tolerate the pre-2026-07-31 shape (bare id) so a cached JSON with fresh JS
    // still renders: try the stated fallback, then the other side.
    return rec(entry, fallbackSide) || rec(entry, fallbackSide === "hit" ? "pit" : "hit");
  }
  // player_links map (mlbam -> merged-card key), resolved once at boot so
  // nameLink can build hrefs synchronously (mirrors mlbstats.js / pal.js).
  var LINKS = null;

  // ---- helpers --------------------------------------------------------------
  function el(id) { return document.getElementById(id); }
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
    return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }
  function num(v, d) { return (v == null || isNaN(v)) ? "-" : Number(v).toFixed(d == null ? 1 : d); }
  // player_links is keyed by mlbam ALONE by design: it maps a PERSON to their
  // merged MLB card, and a two-way player has exactly one of those. This is not
  // the side-keyed player-record lookup (that is rec()/recOf()) and the two must
  // not be confused - keying a RECORD lookup on mlbam alone is the Ohtani bug.
  function hrefFor(mlbam) {
    var e = LINKS && LINKS.byMlbam && LINKS.byMlbam[String(mlbam)];
    return (e && e.key) ? ("/projections/#player=" + e.key) : null;
  }
  function nameLink(mlbam, name) {
    var h = hrefFor(mlbam);
    if (h) return '<a class="fantasy-name-link" href="' + esc(h) + '">' + esc(name) + "</a>";
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
    // Keyed by mlbam AND side, the same composite S.byId uses. A single pool is
    // one-sided today so a bare mlbam would not actually collide here, but an
    // mlbam-only map is exactly the shape that produced the Ohtani bug: any
    // future combined-pool caller would silently drop one of his two rows.
    var out = {};
    pool.forEach(function (p, i) {
      var t = 0;
      cats.forEach(function (c) { t += z[c][i]; });
      out[p.mlbam + "|" + p.side] = t;
    });
    return out;
  }
  function isRoto() { return S.system === "5x5" || S.system === "4x4"; }
  // Score every player in `ids` under the current system → [{p, score}] desc.
  function scored(ids, side) {
    var pool = (ids || []).map(function (m) { return rec(m, side); }).filter(Boolean);
    if (isRoto()) {
      var rv = rotoValue(pool, side);
      return pool.map(function (p) { return { p: p, score: rv[p.mlbam + "|" + p.side] }; })
                 .sort(function (a, b) { return b.score - a.score; });
    }
    return pool.map(function (p) { return { p: p, score: scorePoints(p.ros, side) }; })
               .sort(function (a, b) { return (b.score || -1e9) - (a.score || -1e9); });
  }
  function scoreLabel() { return isRoto() ? "Value" : (S.system === "sabr" ? "SABR pts" : "FG pts"); }

  // ---- card boards ----------------------------------------------------------
  // WHICH SURFACES BECAME CARDS, and why. Row counts measured off
  // data/fantasy.json (json.load + len on each section list), 2026-07-31:
  //
  //   CONVERTED   ROS Hitters 350 | ROS SP 250 | ROS RP 180 | Dynasty 300
  //     These are the leaderboards. Nine to eleven columns each, 180-350 rows,
  //     and they re-rank live every time the league-scoring selector moves. They
  //     also had NO sort at all: the boards were nailed to the score order, so a
  //     roto manager could not ask "who is left with steals". Sortable headers
  //     are the real win; content-visibility is what makes 350 rows in the DOM
  //     affordable, which in turn let the old 250-row display cap go away.
  //
  //   LEFT AS TABLES (deliberately)
  //     Daily Streamers  26 / 23 / 27 rows per day slate (76 total, ONE day shown)
  //     Two-Start SP     79 rows, 5 columns, one of them a free-text leg list
  //     Buy / Sell       30 + 30, rendered as a deliberate side-by-side pair
  //     Call-up Watch    60 rows, 5 narrow columns
  //     Closer Grid      already a card grid (30 teams x 5 arms), untouched
  //     A 27-row table is scannable in one screen; the same 27 rows as 104px
  //     cards is three screens of scrolling. Buy/Sell would additionally lose
  //     the left-right pairing that IS the surface. Converting these would have
  //     been motion, not improvement.
  //
  // THE PATTERN (prospx/index.html + the .mlb-card block in assets/site.css):
  // fixed-height two-row card, grid-template-rows: minmax(0,1fr) auto so row 2
  // always keeps its own band, minmax(0,...) on the flexible track so a long
  // name cannot blow it out, content-visibility + contain-intrinsic-size for
  // virtualization, org-colour stripe channel, diamond rank chip, and one
  // universal sort map driving header + comparator.
  function _ros(o, k) { var r = o.p.ros || {}; return r[k] == null ? null : r[k]; }
  function _sk(o, k) { var s = o.p.skill || {}; return s[k] == null ? null : s[k]; }
  function f0(v) { return num(v, 0); }
  function f2(v) { return num(v, 2); }
  function f3(v) { return num(v, 3); }
  function scoreFmt(v) { return num(v, isRoto() ? 2 : 0); }
  // Identity block shared by both ROS boards: logo + linked name, then the
  // pos/team sub-line the old table spent a whole column on.
  function rosIdentity(o) {
    var p = o.p;
    return '<div class="ff-id"><span class="mlb-name">' + teamLogo(p.team) + " " + nameLink(p.mlbam, p.name) +
      '</span><span class="mlb-sub">' + esc(p.pos || "") + (p.team ? " &middot; " + esc(p.team) : "") + "</span></div>";
  }

  // ---- universal column map -------------------------------------------------
  // ONE array per board drives the card cells, the aligned sort header, the tape
  // sort bar AND the comparator, so those four can never drift apart (the
  // declarative REL_COLS pattern from assets/mlbstats.js, adapted to cards).
  //   where "head" -> a row-1 card cell and a track in .mlb-card-head
  //   where "tape" -> a row-2 chip and a button in the sort bar
  //   asc: true    -> lower is better, so a FRESH click sorts ascending
  // get(row) receives the row the board renders: {p, score} for the ROS boards,
  // the served dynasty object for Dynasty. No model math lives here; the
  // formatters only round numbers that arrived in the artifact.
  var SCORE_TITLE = "Rest-of-season value in the league format picked above. Points formats are the dot product of the projection and that format's weight table; roto formats are pooled category z-scores.";
  var HIT_COLS = [
    { key: "rank", label: "#", where: "head", track: "38px", kind: "rank",
      title: "Board position under the current sort", get: function (o) { return o.score; } },
    { key: "name", label: "Player", where: "head", track: "minmax(0,1.7fr)", kind: "name", text: true, asc: true,
      title: "Sort by name", get: function (o) { return o.p.name; }, cell: rosIdentity },
    { key: "score", label: scoreLabel, where: "head", track: "94px", title: SCORE_TITLE,
      get: function (o) { return o.score; }, fmt: scoreFmt, strong: true },
    { key: "hem_plus", label: "HEM+", term: "hem_plus", where: "head", track: "76px",
      get: function (o) { return _sk(o, "hem_plus"); }, fmt: f0 },
    { key: "hr", label: "HR", where: "tape", get: function (o) { return _ros(o, "hr"); }, fmt: f0 },
    { key: "r", label: "R", where: "tape", get: function (o) { return _ros(o, "r"); }, fmt: f0 },
    { key: "rbi", label: "RBI", where: "tape", get: function (o) { return _ros(o, "rbi"); }, fmt: f0 },
    { key: "sb", label: "SB", where: "tape", get: function (o) { return _ros(o, "sb"); }, fmt: f0 },
    { key: "avg", label: "AVG", where: "tape", get: function (o) { return _ros(o, "avg"); }, fmt: f3 },
    { key: "obp", label: "OBP", where: "tape", get: function (o) { return _ros(o, "obp"); }, fmt: f3 }
  ];
  // SP and RP share every column but the skill index and the role counter, so
  // one factory emits both rather than two near-copies that drift apart.
  function pitCols(isRp) {
    return [
      { key: "rank", label: "#", where: "head", track: "38px", kind: "rank",
        title: "Board position under the current sort", get: function (o) { return o.score; } },
      { key: "name", label: "Pitcher", where: "head", track: "minmax(0,1.7fr)", kind: "name", text: true, asc: true,
        title: "Sort by name", get: function (o) { return o.p.name; }, cell: rosIdentity },
      { key: "score", label: scoreLabel, where: "head", track: "94px", title: SCORE_TITLE,
        get: function (o) { return o.score; }, fmt: scoreFmt, strong: true },
      isRp
        ? { key: "rem_plus", label: "REM+", term: "rem_plus", where: "head", track: "76px",
            get: function (o) { return _sk(o, "rem_plus"); }, fmt: f0 }
        : { key: "sem_plus", label: "SEM+", term: "sem_plus", where: "head", track: "76px",
            get: function (o) { return _sk(o, "sem_plus"); }, fmt: f0 },
      { key: "ip", label: "IP", where: "tape", get: function (o) { return _ros(o, "ip"); }, fmt: f0 },
      { key: "k", label: "K", where: "tape", get: function (o) { return _ros(o, "k"); }, fmt: f0 },
      { key: "era", label: "ERA", where: "tape", asc: true, get: function (o) { return _ros(o, "era"); }, fmt: f2 },
      { key: "whip", label: "WHIP", where: "tape", asc: true, get: function (o) { return _ros(o, "whip"); }, fmt: f2 },
      isRp
        ? { key: "sv", label: "SV", where: "tape", get: function (o) { return _ros(o, "sv"); }, fmt: f0 }
        : { key: "qs", label: "QS", where: "tape", get: function (o) { return _ros(o, "qs"); }, fmt: f0 }
    ];
  }
  // Dynasty: 300 served rows, nine columns, the largest single board here. Cards
  // buy it the same three things the ROS boards get, plus room for the surplus
  // number the export has always carried and the table never showed.
  var DYN_COLS = [
    { key: "rank", label: "#", where: "head", track: "38px", kind: "rank", asc: true,
      title: "Served dynasty rank from the eFV display blend. The diamond always shows the SERVED rank, never the position under an ad-hoc sort, so re-sorting the board cannot renumber the served order.",
      get: function (d) { return d.rank; } },
    { key: "name", label: "Prospect", where: "head", track: "minmax(0,1.7fr)", kind: "name", text: true, asc: true,
      title: "Sort by name", get: function (d) { return d.name; },
      cell: function (d) {
        return '<div class="ff-id"><span class="mlb-name">' + teamLogo(d.org) + " " + nameLink(d.mlbam, d.name) +
          '</span><span class="mlb-sub">' + esc(d.pos || "") + (d.org ? " &middot; " + esc(d.org) : "") + "</span></div>";
      } },
    { key: "efv", label: "eFV", term: "xfv", where: "head", track: "72px", strong: true,
      title: "The eFV board grade - the same number the PROSPX board and Call-up Watch serve for this prospect - rounded to NEAREST (eFV and plus-stats round to nearest; consensus FV grades display as ceiling). The dynasty rank blends it with star odds, bust odds, ETA and surplus.",
      get: function (d) { return d.efv; }, fmt: f0 },
    { key: "eta", label: "ETA", where: "head", track: "72px", asc: true,
      get: function (d) { return d.eta; }, cell: function (d) { return esc(d.eta || "-"); } },
    { key: "tier", label: "Tier", where: "head", track: "96px", asc: true,
      title: "Dynasty tier, bucketed off the served rank",
      get: function (d) { return d.rank; },
      cell: function (d) {
        var cls = d.tier === "Elite" ? " ff-tier-elite" : (d.tier === "Tier 1" ? " ff-tier-one" : "");
        return '<span class="ff-tier' + cls + '">' + esc(d.tier) + "</span>";
      } },
    { key: "star", label: "Star", term: "star_odds", where: "tape",
      get: function (d) { return d.star; },
      cell: function (d) { return d.star == null ? "-" : num(d.star, 0) + "%"; } },
    { key: "bust", label: "Bust", term: "bust_prob", where: "tape", asc: true,
      get: function (d) { return d.bust; },
      cell: function (d) { return d.bust == null ? "-" : num(d.bust, 0) + "%"; } },
    { key: "surplus", label: "Surplus", where: "tape",
      title: "Projected surplus value in $M, read verbatim off the served eFV export. It is one term in the dynasty blend and was never displayed on the old table.",
      get: function (d) { return d.surplus; },
      cell: function (d) { return d.surplus == null ? "-" : "$" + num(d.surplus, 0) + "M"; } },
    { key: "band_hi", label: "Outlook", where: "tape",
      title: "10th-to-90th percentile career-value band. Sorts on the P90 (ceiling) end.",
      get: function (d) { return (d.band || [])[1]; },
      cell: function (d) {
        var b = d.band || [];
        return (b[0] != null && b[1] != null) ? ("$" + num(b[0], 0) + "-" + num(b[1], 0) + "M") : "-";
      } }
  ];

  // ---- shared card machinery ------------------------------------------------
  function colByKey(cols, k) {
    var out = null;
    (cols || []).forEach(function (c) { if (c.key === k) out = c; });
    return out;
  }
  function headCols(cols) { return cols.filter(function (c) { return c.where === "head"; }); }
  function tapeCols(cols) { return cols.filter(function (c) { return c.where === "tape"; }); }
  function labelOf(c) { return typeof c.label === "function" ? c.label() : c.label; }
  // Glossary terms are wired on the header and sort bar ONLY. Putting data-gl on
  // the per-card chip labels would hand EEPHUS_GL 350 x 6 tooltip targets on one
  // board, which is the sort of thing that makes a page feel slow.
  function glossLbl(c) {
    var l = esc(labelOf(c));
    return c.term ? '<span class="g-term" data-gl="' + esc(c.term) + '">' + l + "</span>" : l;
  }
  // Missing values sort LAST in BOTH directions (the mlbstats.js / trademachine
  // convention) so a blank never wins a leaderboard by being blank.
  function sortRowsBy(rows, cols, st) {
    var col = colByKey(cols, st.key);
    if (!col || !col.get) return rows.slice();
    var out = rows.slice();
    out.sort(function (a, b) {
      var va = col.get(a), vb = col.get(b);
      if (col.text) {
        var sa = va == null ? "" : String(va), sb = vb == null ? "" : String(vb);
        if (!sa && !sb) return 0;
        if (!sa) return 1;
        if (!sb) return -1;
        return st.asc ? sa.localeCompare(sb) : sb.localeCompare(sa);
      }
      var na = (va == null || isNaN(va)) ? null : Number(va);
      var nb = (vb == null || isNaN(vb)) ? null : Number(vb);
      if (na == null && nb == null) return 0;
      if (na == null) return 1;
      if (nb == null) return -1;
      return st.asc ? na - nb : nb - na;
    });
    return out;
  }
  // Sort affordance shared by the aligned header and the tape sort bar: a real
  // keyboard button with aria-sort and a direction arrow (the mlbstats.js /
  // projections.js a11y contract, which /fantasy/ did not meet at all before).
  function sortBtn(c, st) {
    var on = st.key === c.key;
    return '<span role="button" tabindex="0" data-ffsort="' + esc(c.key) + '" aria-sort="' +
      (on ? (st.asc ? "ascending" : "descending") : "none") + '"' +
      (c.title ? ' title="' + esc(c.title) + '"' : "") + ">" + glossLbl(c) +
      (on ? (st.asc ? " ▴" : " ▾") : "") + "</span>";
  }
  function cellValue(c, row) {
    if (c.cell) return c.cell(row);
    var v = c.get ? c.get(row) : null;
    if (v == null) return "-";
    return c.fmt ? c.fmt(v) : esc(v);
  }
  // Row-1 cell. The rank is the diamond chip, the name cell is a block, and
  // everything else is a labelled right-aligned metric.
  function cardCell(c, row, rk) {
    if (c.kind === "rank") return '<span class="ff-rank"><span class="ff-rank-i">' + esc(rk) + "</span></span>";
    if (c.kind === "name") return cellValue(c, row);
    return '<span class="mlb-metric' + (c.strong ? " ff-strong" : "") + '"><span class="mlb-metric-label">' +
      glossLbl(c) + "</span>" + cellValue(c, row) + "</span>";
  }
  // The stripe rides the same custom property the PROSPX row and the Lane B MLB
  // cards use (--org-color). Fantasy has NO org-colour source on the client
  // (ORG_COLORS lives inside prospx/index.html and is not shared), so the stripe
  // carries the board's own tier signal instead, in var() tokens only.
  function stripeFor(rk) {
    if (rk <= 10) return "var(--accent-gold)";
    if (rk <= 50) return "var(--accent-cyan)";
    return "var(--border)";
  }
  function dynStripe(d) {
    if (d.tier === "Elite") return "var(--accent-gold)";
    if (d.tier === "Tier 1") return "var(--accent-cyan)";
    if (d.tier === "Tier 2") return "var(--accent-green)";
    return "var(--border)";
  }
  function renderCards(rows, cols, st, opts) {
    opts = opts || {};
    var hcols = headCols(cols), tcols = tapeCols(cols);
    var tracks = hcols.map(function (c) { return c.track; }).join(" ");
    var sorted = sortRowsBy(rows || [], cols, st);
    var body = sorted.map(function (row, i) {
      var rk = opts.rankOf ? opts.rankOf(row, i) : (i + 1);
      var href = opts.hrefOf ? opts.hrefOf(row) : null;
      var chips = tcols.map(function (c) {
        return '<div class="mlb-chip"><b>' + esc(labelOf(c)) + "</b>" + cellValue(c, row) + "</div>";
      }).join("");
      return '<div class="mlb-card ff-card" style="--org-color:' +
        (opts.stripeOf ? opts.stripeOf(row, rk) : stripeFor(rk)) + ";grid-template-columns:" + tracks + '"' +
        (href ? ' tabindex="0" role="button" data-ffhref="' + esc(href) + '"' : "") + ">" +
        hcols.map(function (c) { return cardCell(c, row, rk); }).join("") +
        '<div class="mlb-tape"><div class="mlb-tape-inner">' + chips + "</div></div></div>";
    }).join("");
    if (!body) return '<div class="fantasy-note">' + esc(opts.empty || "No rows to show yet.") + "</div>";
    var head = '<div class="mlb-card-head ff-card-head" style="grid-template-columns:' + tracks + '">' +
      hcols.map(function (c) { return sortBtn(c, st); }).join("") + "</div>";
    // The tape stats are not track-aligned with the header (they live in row 2),
    // so they get their own sort bar rather than a fake column heading floating
    // above a chip that may have scrolled sideways inside its own box.
    var bar = tcols.length
      ? '<div class="ff-sortbar"><span class="ff-sortbar-lbl">Sort by</span>' +
        tcols.map(function (c) { return sortBtn(c, st); }).join("") + "</div>"
      : "";
    return bar + head + '<div class="mlb-card-list ff-card-list">' + body + "</div>";
  }

  // ---- section renderers ----------------------------------------------------
  // The 250-row display cap the ROS tables carried is gone: content-visibility
  // means off-screen cards cost nothing to keep in the DOM, so ROS Hitters now
  // shows all 350 served rows instead of truncating 100 of them.
  function boardHitter(ids) {
    return renderCards(scored(ids, "hit"), HIT_COLS, SORT.ros_hitter, {
      hrefOf: function (o) { return hrefFor(o.p.mlbam); },
      empty: "Rest-of-season hitter projections populate on the nightly build."
    });
  }
  function boardPitcher(ids, isRp) {
    return renderCards(scored(ids, "pit"), pitCols(isRp), isRp ? SORT.ros_rp : SORT.ros_sp, {
      hrefOf: function (o) { return hrefFor(o.p.mlbam); },
      empty: "Rest-of-season pitcher projections populate on the nightly build."
    });
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
  // STAYS A TABLE: one day slate at a time, measured at 26 / 23 / 27 rows.
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
    // A deep-linked #day= that is not in the served window (yesterday's link,
    // opened this morning) is not an error state: it snaps to the first slate,
    // exactly as an empty S.streamerDay does. That is why readHash does not
    // validate the date against the slate itself - only this render knows it.
    S.streamerDay0 = days[0];
    if (!S.streamerDay || days.indexOf(S.streamerDay) < 0) S.streamerDay = days[0];
    var pills = days.map(function (d) {
      var on = d === S.streamerDay;
      return '<button type="button" class="ff-daypill' + (on ? " active" : "") + '" data-streamerday="' + esc(d) +
        '" role="tab" aria-selected="' + (on ? "true" : "false") + '">' + streamerDayLabel(d) + "</button>";
    }).join("");
    var rows = (byDay[S.streamerDay] || []).slice(0, 40).map(function (st, i) {
      var p = rec(st.mlbam, "pit") || {}, s = p.skill || {};   // probables are pitchers
      return '<tr><td class="ff-rk">' + (i + 1) + '</td><td>' + esc(st.date) + '</td><td class="ff-nm">' +
        nameLink(st.mlbam, st.name) + " " + teamLogo(st.team) + '</td><td>@ ' + esc(st.opp_org) +
        " (Off+ " + num(st.opp_off, 0) + ')</td><td class="ff-sc">' + num(st.per_start_fgp, 1) + "</td><td>" +
        (s.sem_plus != null ? num(s.sem_plus, 0) : "-") + "</td><td>" + esc(st.venue || "") + "</td></tr>";
    }).join("");
    return '<div class="fantasy-note">Every announced probable start over the next 3 days, ranked by matchup-adjusted expected points (weaker opposing offense ranks higher). Pick a day below. Scored in FanGraphs Points; switch formats above to re-rank the ROS boards.</div>' +
      '<div class="ff-daypills" role="tablist" aria-label="Streamer day">' + pills + "</div>" +
      '<table class="fantasy-table"><thead><tr><th>#</th><th>Date</th><th>Pitcher</th><th>Opponent</th><th>Exp pts</th><th>SEM+</th><th>Park</th></tr></thead><tbody>' + rows + "</tbody></table>";
  }
  // STAYS A TABLE: 79 rows, and the Matchups column is a free-text leg list that
  // would fight a fixed-height card box.
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
  // STAYS A TABLE: 30 + 30 rows in a deliberate side-by-side pair. Cards would
  // break the left-right comparison, which is the entire point of the surface.
  function renderBuySell() {
    function col(ids, label, cls) {
      var rows = (ids || []).slice(0, 30).map(function (e) {
        var p = recOf(e, "hit"); if (!p) return "";
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
    // Copy contract (2026-08-19, test_fantasy_claims.py): the registry row
    // fantasy_buy_sell records that NO committed measurement exists that a
    // large luck gap regresses rather than persists. So this note states the
    // gap direction and stops: no "due to improve", no luck causality in the
    // column headers. The screen posture line mirrors the registry row.
    return '<div class="fantasy-note">Regression screen from the expected-stat gaps (hitters: xHEM+ − HEM+; pitchers: xERA/xwOBA vs actual). A positive gap means results sit behind the expected stats (buy-low screen); negative means results sit ahead (sell-high screen). Whether a gap closes or persists is unmeasured: this is a screen, it reorders nothing served elsewhere and prices nothing. A mech trend chip flags a 5+ point move in per-season Swing+ (Will Cahoon) - swing-mechanics context only, never part of the ranking.</div>' +
      '<div class="fantasy-cols">' + col(sec.buy_low, "Buy-Low (behind x-stats)", "ff-pos") + col(sec.sell_high, "Sell-High (ahead of x-stats)", "ff-neg") + "</div>";
  }
  // ALREADY A CARD GRID: 30 team cards of 5 arms each. Untouched.
  function renderClosers() {
    var depth = (S.data.sections || {}).closer_depth || {};
    var teams = Object.keys(depth).sort();
    var cards = teams.map(function (tm) {
      var lst = (depth[tm] || []).map(function (m, i) {
        var p = rec(m, "pit"); if (!p) return "";   // bullpen depth is pitchers
        var s = p.skill || {};
        var role = i === 0 ? '<span class="ff-closer">CLOSER</span>' : '<span class="ff-hc">' + (i === 1 ? "next" : "depth") + "</span>";
        return '<div class="ff-relief">' + role + " " + nameLink(p.mlbam, p.name) +
          ' <span class="ff-dim">gmLI ' + num(s.gmli, 2) + " · " + num(s.saves, 0) + "sv · REM+ " + num(s.rem_plus, 0) + "</span></div>";
      }).join("");
      return '<div class="fantasy-team-card"><div class="ff-team-hd">' + teamLogo(tm) + " " + esc(tm) + "</div>" + lst + "</div>";
    }).join("");
    // Copy contract (2026-08-19, test_fantasy_claims.py): fantasy_closer_depth
    // is a role-ORDER display and the save-share model LOST to the pace rule
    // (gate RED 2026-08-16). The note may describe the ordering rule; it may
    // not call the top arm "likely" anything or imply a model picks saves.
    return '<div class="fantasy-note">Bullpen pecking order: gmLI carries the ordering, saves and REM+ break ties. A role-order read, not a saves projection - nothing here prices saves. The top arm holds the closer slot in this order, the rest are save handcuffs. Grab the next-in-line before the save chance opens.</div><div class="fantasy-grid">' + cards + "</div>";
  }
  // STAYS A TABLE: 60 rows, five narrow columns, nothing a card would help.
  function renderCallups() {
    var list = (S.data.sections || {}).callup_watch || [];
    if (!list.length) return '<div class="fantasy-note">Call-up watch populates from the PROSPX prospect board on the nightly build (fantasy-relevant prospects near their ETA).</div>';
    var rows = list.map(function (c) {
      return "<tr><td class=\"ff-nm\">" + nameLink(c.mlbam, c.name) + "</td><td>" + esc(c.org) + "</td><td>" + esc(c.pos) +
        // eFV (round-to-nearest) leads; consensus ceil is the fallback.
        "</td><td>" + esc(c.eta) + "</td><td>" +
        (c.fvE != null ? String(Math.round(c.fvE)) : (c.fv != null ? String(Math.ceil(c.fv)) : "-")) + "</td></tr>";
    }).join("");
    return '<div class="fantasy-note">Prospects near the majors with fantasy upside - stash before the call.</div>' +
      '<table class="fantasy-table"><thead><tr><th>Prospect</th><th>Org</th><th>Pos</th><th>ETA</th><th>FV</th></tr></thead><tbody>' + rows + "</tbody></table>";
  }
  function renderDynasty() {
    var list = (S.data.sections || {}).dynasty || [];
    if (!list.length) return '<div class="fantasy-note">Dynasty prospect rankings populate from the eFV model on the nightly build.</div>';
    return '<div class="fantasy-note">Dynasty prospect value from our flagship eFV model - ranked by a blend that keeps the eFV grade primary, then rewards star upside (star-outcome odds), penalizes floor risk (bust odds), and factors ETA proximity and projected surplus. Outlook is each prospect\'s 10th-to-90th percentile career-value band. This is a display ranking over served eFV numbers, not a separate model.</div>' +
      renderCards(list, DYN_COLS, SORT.dynasty, {
        rankOf: function (d) { return d.rank; },
        stripeOf: dynStripe,
        hrefOf: function (d) { return hrefFor(d.mlbam); },
        empty: "Dynasty prospect rankings populate from the eFV model on the nightly build."
      });
  }

  // Column map for the section currently on screen, so the sort wiring can read
  // a column's preferred first direction without each board repeating itself.
  function colsFor(section) {
    if (section === "ros_hitter") return HIT_COLS;
    if (section === "ros_sp") return pitCols(false);
    if (section === "ros_rp") return pitCols(true);
    if (section === "dynasty") return DYN_COLS;
    return null;
  }
  function renderSection() {
    var sec = S.data.sections || {}, root = el("fantasy-app-root");
    if (!root) return;
    var html;
    switch (S.section) {
      case "streamers": html = tableStreamers(sec.daily_streamers); break;
      case "two_start": html = tableTwoStart(sec.two_start); break;
      case "ros_sp": html = boardPitcher(sec.ros_sp, false); break;
      case "ros_rp": html = boardPitcher(sec.ros_rp, true); break;
      case "ros_hitter": html = boardHitter(sec.ros_hitter); break;
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
        writeHash();
      });
    });
    // Sort headers + tape sort bar. Click AND Enter/Space, with focus restored
    // to the same control after the re-render replaces it (the bindSortKeys
    // contract in assets/mlbstats.js). A repeat click flips direction; a fresh
    // column opens in ITS preferred direction, so ERA / WHIP / Bust go low-first.
    root.querySelectorAll("[data-ffsort]").forEach(function (h) {
      function fire(refocus) {
        var st = SORT[S.section];
        if (!st) return;
        var k = h.getAttribute("data-ffsort"), c = colByKey(colsFor(S.section), k);
        if (st.key === k) st.asc = !st.asc;
        else { st.key = k; st.asc = !!(c && c.asc); }
        renderSection();
        writeHash();
        if (!refocus) return;
        var again = root.querySelector('[data-ffsort="' + k + '"]');
        if (again && again.focus) again.focus();
      }
      h.addEventListener("click", function () { fire(false); });
      h.addEventListener("keydown", function (e) {
        if (e.key !== "Enter" && e.key !== " ") return;
        e.preventDefault();
        fire(true);
      });
    });
    // Whole-card activation, matching the PROSPX row and the Lane B MLB cards.
    // Clicks that landed on a real control inside the card are left alone.
    root.querySelectorAll("[data-ffhref]").forEach(function (c) {
      function open() { location.href = c.getAttribute("data-ffhref"); }
      // The guard must EXCLUDE THE CARD ITSELF. The card carries role="button"
      // (see the row builder above), and Element.closest() starts at the element it
      // is called on, so a plain `closest("a,button,[role=button]")` matched the card
      // on every click and returned before open() ever ran. That shipped whole-card
      // activation as dead on all four converted boards: ~1,080 elements announced
      // as buttons that did nothing, by mouse or by keyboard.
      // Resolving the hit target and comparing it to the card keeps real inner
      // controls (links, buttons, and the role=button sort chips) working while
      // letting a click on the card body through.
      function onCard(e) {
        var t = e.target.closest("a,button,[role=button]");
        return !t || t === c;
      }
      c.addEventListener("click", function (e) {
        if (onCard(e)) open();
      });
      c.addEventListener("keydown", function (e) {
        if (e.key !== "Enter" && e.key !== " ") return;
        if (!onCard(e)) return;
        e.preventDefault();
        open();
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
        renderSelector(); renderSection(); writeHash();
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
  // Paint S.section onto the section nav (the showSection pattern from
  // assets/mlbstats.js). The shell ships with Daily Streamers hard-coded active,
  // so a deep-linked #section=dynasty needs this or it renders the dynasty board
  // under a nav that still says, and announces, Daily Streamers.
  function syncTabs() {
    document.querySelectorAll(".mlbstats-sectionbtn[data-fantasysection]").forEach(function (b) {
      var on = b.getAttribute("data-fantasysection") === S.section;
      b.classList.toggle("active", on);
      b.setAttribute("aria-selected", on ? "true" : "false");
    });
  }
  function wireTabs() {
    document.querySelectorAll(".mlbstats-sectionbtn[data-fantasysection]").forEach(function (b) {
      b.addEventListener("click", function () {
        S.section = b.getAttribute("data-fantasysection");
        syncTabs();
        renderSection();
        writeHash();
      });
    });
  }

  // ---- hash router ----------------------------------------------------------
  // /fantasy/ kept every bit of its state in memory: a refresh dropped you back
  // on Daily Streamers in FanGraphs Points, nothing outside the module could
  // point at a board inside it, and the homepage cross-module card had to link
  // the bare page while its neighbours all deep-linked a row.
  //
  // GRAMMAR (readHash/writeHash follow assets/mlbstats.js; every key is optional
  // and every key is validated, so a hand-edited or stale URL degrades to the
  // default rather than to a broken board):
  //   #section=streamers|two_start|ros_sp|ros_rp|ros_hitter|buysell|closers|callups|dynasty
  //   #sys=<scoring id>      any id the SERVED scoring_catalog carries (fgp|sabr|5x5|4x4 today)
  //   #day=YYYY-MM-DD        the Daily Streamers slate
  //   #hsort= #spsort= #rpsort= #dsort=   <column>.<a|d>, one per card board
  //                          (ros_hitter / ros_sp / ros_rp / dynasty)
  // section is always written; everything else only when it is off its default,
  // which keeps a shared URL short and readable.
  //
  // THERE IS NO PLAYER DEEP-LINK, because there is no player detail HERE: every
  // name on this module is an outbound link to the merged card at
  // /projections/#player=<key> (see nameLink/hrefFor above). A "#player=" on
  // /fantasy/ would have to invent a surface that does not exist, so the deepest
  // this module goes is the board, and the merged card already owns the player.

  // The section names renderSection switches on, as an ALTERNATION baked into
  // the regex rather than a lookup in a map. A map would have accepted
  // "#section=constructor" - inherited off Object.prototype, truthy, and enough
  // to render the fallback board under a nav with no tab marked active.
  var SECTIONS = ["streamers", "two_start", "ros_sp", "ros_rp", "ros_hitter",
                  "buysell", "closers", "callups", "dynasty"];
  var SECTION_PAT = SECTIONS.join("|");
  var LAST_HASH = null;
  // Each key is anchored to a separator, so a longer key can never be matched by
  // a shorter one's regex (the mlbstats.js "sview= must not match view=" rule -
  // here it is what keeps "spsort=" out of the "dsort=" and "hsort=" reads).
  function hashParam(h, key, pat) {
    var m = new RegExp("(?:^#|[#&])" + key + "=(" + pat + ")(?:&|$)").exec(h || "");
    return m ? m[1] : null;
  }
  // A sort is only honoured if the named column EXISTS on that board and can be
  // compared there. colsFor + colByKey are the same pair the click handler uses,
  // and sortRowsBy needs exactly one thing from a column - a get() - so that is
  // the test. Anything else leaves the board on its served default instead of
  // sorted by a column it does not have.
  function readSort(h, key, board) {
    var v = hashParam(h, key, "[A-Za-z0-9_]+\\.[ad]");
    if (!v) return;
    var i = v.lastIndexOf("."), k = v.slice(0, i), c = colByKey(colsFor(board), k);
    if (!c || !c.get) return;
    SORT[board].key = k;
    SORT[board].asc = (v.slice(i + 1) === "a");
  }
  // Runs from onData, after S.system has taken the served catalog default and
  // before the first paint, so every value this touches already holds what a
  // hash-less load would have left it on. An absent or rejected key is simply
  // not applied, which is what makes a bare /fantasy/ behave exactly as before.
  function readHash() {
    var h = location.hash || "";
    var s = hashParam(h, "section", SECTION_PAT);
    if (s) S.section = s;
    // Validated against the SERVED catalog rather than a literal list: a format
    // added to or dropped from fantasy_scoring.SCORING_CATALOG needs no change
    // here, and a retired id cannot leave the pool scored by a weight table the
    // payload no longer carries.
    var sys = hashParam(h, "sys", "[A-Za-z0-9_]+");
    var known = ((S.data && S.data.scoring_catalog) || []).filter(function (c) { return c.id === sys; });
    if (sys && known.length) S.system = sys;
    // Not checked against the slate here - tableStreamers owns that window and
    // snaps an out-of-range day to the first served date (see its comment).
    var day = hashParam(h, "day", "\\d{4}-\\d{2}-\\d{2}");
    if (day) S.streamerDay = day;
    readSort(h, "hsort", "ros_hitter");
    readSort(h, "spsort", "ros_sp");
    readSort(h, "rpsort", "ros_rp");
    readSort(h, "dsort", "dynasty");
  }
  function pushSort(parts, key, board) {
    var st = SORT[board], d = SORT_DEFAULTS[board];
    if (!st || !st.key) return;
    if (d && st.key === d.key && !!st.asc === !!d.asc) return;
    parts.push(key + "=" + st.key + "." + (st.asc ? "a" : "d"));
  }
  // Composes the WHOLE module state on every section/scoring/day/sort change, so
  // a copied URL restores what the reader is looking at, and one replaceState
  // writes it. Never called during boot or during a render: the hash of a page
  // nobody has touched stays empty.
  function writeHash() {
    var parts = ["section=" + S.section];
    var def = ((S.data && S.data.scoring_catalog) || []).filter(function (c) { return c.default; })[0];
    if (S.system && S.system !== (def ? def.id : "fgp")) parts.push("sys=" + S.system);
    // Only once the reader has moved off the slate the board opened on. Writing
    // the default day would stamp today's date into every shared /fantasy/ URL,
    // and that date is wrong by tomorrow morning.
    if (S.streamerDay && S.streamerDay !== S.streamerDay0) parts.push("day=" + S.streamerDay);
    pushSort(parts, "hsort", "ros_hitter");
    pushSort(parts, "spsort", "ros_sp");
    pushSort(parts, "rpsort", "ros_rp");
    pushSort(parts, "dsort", "dynasty");
    LAST_HASH = "#" + parts.join("&");
    try { history.replaceState(null, "", LAST_HASH); } catch (e) { /* the hash is an optional nicety */ }
  }
  // history.replaceState does not fire hashchange, so this only ever sees a hash
  // the READER changed: an edited URL, a same-page anchor, a Back across a link
  // that carried one. LAST_HASH is compared anyway. The prospx lesson is that a
  // hashchange handler which re-renders on an echo of its own write ejects the
  // user mid-scroll, and one string compare is cheaper than discovering that a
  // browser disagrees about which writes are silent.
  function onHashChange() {
    if (!S.data) return;                       // pre-data hashes are read by onData
    if ((location.hash || "") === LAST_HASH) return;
    readHash();
    renderSelector(); syncTabs(); renderSection();
  }
  window.addEventListener("hashchange", onHashChange);

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
    // Keyed by mlbam AND side. A two-way player has TWO player records (the
    // exporter emits both, correctly, inside its `for side in ("hit","pit")`
    // loop), and keying on mlbam alone was last-write-wins: "pit" is appended
    // second, so it silently clobbered the hitter record. Shohei Ohtani was
    // rendering his 172.6 pitcher points on the ROS Hitters board, which put him
    // at rank 15 instead of rank 3 with his real 284.8, and handed renderBuySell
    // a pitcher skill object for a row ranked in on hitter luck.
    S.byId = {};
    d.players.forEach(function (p) { S.byId[p.mlbam + "|" + p.side] = p; });
    var def = (d.scoring_catalog || []).filter(function (c) { return c.default; })[0];
    S.system = def ? def.id : "fgp";
    var banner = el("fantasy-banner");
    if (banner) banner.innerHTML = '<div class="fantasy-asof">' + (d.n_players || 0) + " players · rest-of-season, " +
      Math.round((d.season_fraction || 0) * 100) + "% of " + esc(d.season) + " played · scored in your league format</div>";
    // Deep-link restore, between the defaults and the first paint so a restored
    // section/scoring/sort renders once rather than flashing Daily Streamers in
    // FanGraphs Points first. injectDynastyTab runs before syncTabs because the
    // Dynasty button does not exist in the shell markup, and a deep link to
    // #section=dynasty has to find a tab to mark active.
    readHash();
    renderSelector(); injectDynastyTab(); wireTabs(); syncTabs(); renderSection();
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
  // The CARD styles are NOT here - they live next to the shared .mlb-card block
  // in assets/site.css, because the fantasy cards are the same system the
  // Projections and Free Agency boards run on and one copy is the point.
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
