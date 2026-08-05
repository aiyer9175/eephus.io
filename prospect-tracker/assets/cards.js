/* Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
 * Unauthorized copying of this file, via any medium is strictly prohibited
 * Proprietary and confidential
 * Written by Noah J. Dengler (@ARKNDJL), 2026 */

// =============================================================================
// eephus.io - Baseball Card Market (/cards/)
// =============================================================================
// Renders data/card_market.json (card_market_export.py). Three boards plus a
// method section:
//
//   Buy screen  cards whose player ranks higher on talent than the card ranks
//               on price, inside their own tier
//   Movers      biggest index change against the prior window
//   Watchlist   every tracked card, including the ones with no index yet
//   Method      what the index is, what it is not, and the disclaimers
//
// WHAT THIS PAGE SHOWS, AND WHAT IT DOES NOT
// ------------------------------------------
// Every price here is the eephus Card Index: a grade-mix adjusted trimmed
// median of public sold prices, published on a coarse grid. Individual sales,
// listings, sellers and listing titles are NOT republished, and the payload
// does not contain them (test_card_market asserts their absence). The page
// says this in the banner, not only in the method section, because a reader
// who never opens Method still deserves to know what the number is.
//
// v1 IS A SCREEN. The payload carries `screen: true` and the page carries the
// label wherever a signal appears. There is no price-history backtest yet; the
// module is accumulating its own history toward one. Same posture as the PAL
// conversion FIT: a labelled screen is honest, an unlabelled screen is not.
//
// A missing sidecar is a LOUD empty state, never a blank page: /cards/ ships
// before its first export runs, so "not built yet" has to render as words.
(function () {
  "use strict";

  // ---- the module stylesheet ------------------------------------------------
  // assets/cards.css SHIPPED ORPHANED. Rendered in a real browser for the first
  // time on 2026-08-05, /cards/ was serving with site.css only: nothing in
  // build_site.py, in the emitted <head>, or in any script ever referenced
  // cards.css, so all 176 of its lines were dead. Every .cards-* class on the
  // page - the screen banner, the signal chips, the sparkline, the detail
  // drawer, the refractor hairline, and the phone/desktop chip swap that stops
  // the row-1 metrics being printed TWICE - resolved to nothing.
  //
  // Self-loading here fixes it from the asset side with no rebuild, and the
  // guard makes it a no-op the moment a proper versioned <link> lands in the
  // page shell (which is the better permanent home, since a <link> in <head>
  // has no flash). Do not remove the guard: two copies of a sheet is not a bug
  // but it is noise in the network tab.
  (function ensureCSS() {
    try {
      if (document.querySelector('link[rel="stylesheet"][href*="cards.css"]')) return;
      var l = document.createElement("link");
      l.rel = "stylesheet";
      l.href = "/assets/cards.css";
      document.head.appendChild(l);
    } catch (e) { /* no head yet: the page is broken in a bigger way */ }
  })();

  var DATA_URL = "/data/card_market.json";
  var SECTIONS = { buy: 1, movers: 1, watchlist: 1, method: 1 };

  var DATA = null;
  var LOAD_ERROR = false;
  var LINKS = null;               // player_links.json, for the /projections/ linkthrough
  var section = "buy";
  var state = {
    tier: "ALL",
    query: "",
    open: {},                     // card_id -> detail open
    sort: { buy: "gap", movers: "trend", watchlist: "efv" }
  };

  // ---- helpers --------------------------------------------------------------
  function el(id) { return document.getElementById(id); }
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }
  function num(v) { return (v === null || v === undefined || isNaN(v)) ? null : Number(v); }
  function f1(v) { var n = num(v); return n === null ? "-" : n.toFixed(1); }
  // eFV rounds to NEAREST (it is not a scouting FV, which ceilings). The site
  // rule in one place so no cell can drift off it.
  //
  // ONE DECIMAL, ALWAYS. String(Math.round(n*10)/10) drops the trailing zero,
  // so a tabular-nums column read 61.9 / 61 / 60.2 / 58 / 57.4 with the whole
  // numbers hanging a digit short of their neighbours. toFixed(1) is the same
  // rounding, printed to a fixed width.
  function fEfv(v) { var n = num(v); return n === null ? "-" : (Math.round(n * 10) / 10).toFixed(1); }
  function money(v) {
    var n = num(v);
    if (n === null) return "-";
    return "$" + Math.round(n).toLocaleString("en-US");
  }
  function pct(v, signed) {
    var n = num(v);
    if (n === null) return "-";
    return (signed && n > 0 ? "+" : "") + n.toFixed(1) + "%";
  }
  function tokens() {
    return { grid: "var(--border, #2b2b31)", axis: "var(--text-tertiary, #7c808a)",
             up: "var(--accent-green, #1f7a3a)", down: "var(--accent-red, #b91c1c)",
             line: "var(--accent-cyan, #0e7c86)" };
  }
  function hrefFor(mlbam) {
    var e = LINKS && LINKS.byMlbam && LINKS.byMlbam[String(mlbam)];
    return (e && e.key) ? ("/projections/#player=" + e.key) : null;
  }
  function nameLink(c) {
    var h = c.mlbam ? hrefFor(c.mlbam) : null;
    var n = esc(c.name || c.player_key || "Unknown");
    return h ? '<a class="cards-name-link" href="' + esc(h) + '">' + n + "</a>" : n;
  }
  function teamLogo(org) {
    return (window.EEPHUS_HUB && EEPHUS_HUB.teamLogo && org) ? EEPHUS_HUB.teamLogo(org) : "";
  }

  // ---- sparkline ------------------------------------------------------------
  // Inline SVG on resolved CSS tokens, the same shape EEPHUS_HUB.histogram /
  // scatter use (_chartTokens -> var() strings inside the markup), so it is
  // theme-aware with no JS palette and taints no canvas. Points are OUR derived
  // index values from card_index_history; no comp appears in a sparkline.
  function sparkline(points, o) {
    o = o || {};
    var pts = (points || []).filter(function (p) { return num(p.v) !== null; });
    if (pts.length < 2) return '<span class="cards-spark-empty">not enough history yet</span>';
    var W = o.width || 160, H = o.height || 34, pad = 3;
    var vals = pts.map(function (p) { return Number(p.v); });
    var lo = Math.min.apply(null, vals), hi = Math.max.apply(null, vals);
    if (hi <= lo) { hi = lo + 1; }
    var t = tokens();
    var up = vals[vals.length - 1] >= vals[0];
    var d = pts.map(function (p, i) {
      var x = pad + (i / (pts.length - 1)) * (W - pad * 2);
      var y = H - pad - ((Number(p.v) - lo) / (hi - lo)) * (H - pad * 2);
      return (i ? "L" : "M") + x.toFixed(1) + " " + y.toFixed(1);
    }).join(" ");
    var lastX = W - pad;
    var lastY = H - pad - ((vals[vals.length - 1] - lo) / (hi - lo)) * (H - pad * 2);
    return '<svg class="cards-spark" viewBox="0 0 ' + W + " " + H + '" width="' + W +
      '" height="' + H + '" role="img" aria-label="' +
      esc(o.aria || "card index history, " + pts.length + " points") + '">' +
      '<path d="' + d + '" fill="none" stroke="' + (up ? t.up : t.down) + '" stroke-width="1.5"/>' +
      '<circle cx="' + lastX.toFixed(1) + '" cy="' + lastY.toFixed(1) + '" r="2" fill="' +
      (up ? t.up : t.down) + '"/></svg>';
  }

  // ---- filtering / sorting --------------------------------------------------
  function allCards() { return (DATA && DATA.cards) || []; }
  function filtered() {
    var q = (state.query || "").trim().toLowerCase();
    return allCards().filter(function (c) {
      if (state.tier !== "ALL" && (c.tier || "other") !== state.tier) return false;
      if (!q) return true;
      return String(c.name || "").toLowerCase().indexOf(q) >= 0 ||
             String(c.org || "").toLowerCase().indexOf(q) >= 0 ||
             String(c.set || "").toLowerCase().indexOf(q) >= 0;
    });
  }
  function byDesc(key) {
    return function (a, b) {
      var x = num(a[key]), y = num(b[key]);
      if (x === null && y === null) return String(a.card_id).localeCompare(String(b.card_id));
      if (x === null) return 1;
      if (y === null) return -1;
      return y - x;
    };
  }
  function absDesc(key) {
    return function (a, b) {
      var x = num(a[key]), y = num(b[key]);
      if (x === null && y === null) return 0;
      if (x === null) return 1;
      if (y === null) return -1;
      return Math.abs(y) - Math.abs(x);
    };
  }
  // The watchlist order, in ONE place, so the exported graphic cannot list the
  // same cards in a different order than the board on screen.
  function byEfvThenName(a, b) {
    var x = num(a.efv), y = num(b.efv);
    if (x === null && y === null) return String(a.name || "").localeCompare(String(b.name || ""));
    if (x === null) return 1;
    if (y === null) return -1;
    return y - x;
  }

  // ---- card rows ------------------------------------------------------------
  function signalChip(c) {
    var s = c.signal || "unpriced";
    var label = { buy: "Buy screen", fade: "Fade", hold: "Hold", unpriced: "No index" }[s] || s;
    return '<span class="cards-sig cards-sig--' + esc(s) + '">' + esc(label) + "</span>";
  }
  function stripeFor(c) {
    if (c.signal === "buy") return "var(--accent-green)";
    if (c.signal === "fade") return "var(--accent-red)";
    if (c.signal === "hold") return "var(--accent-cyan)";
    return "var(--border)";
  }
  function trendCell(c) {
    var n = num(c.trend_pct);
    if (n === null) return '<span class="cards-flat">-</span>';
    var cls = n > 0 ? "cards-up" : (n < 0 ? "cards-down" : "cards-flat");
    return '<span class="' + cls + '">' + pct(n, true) + "</span>";
  }
  function efvCell(c) {
    var v = fEfv(c.efv);
    if (c.efv_kind === "debuted" && v !== "-") {
      return v + '<span class="proj-dim" title="Retrospective cohort grade, not a forward projection"> hist</span>';
    }
    return v;
  }
  function indexCell(c) {
    if (c.index_usd === null || c.index_usd === undefined) {
      var why = c.index_reason === "thin" ? "thin" : "none";
      return '<span class="cards-noidx" title="' +
        esc(c.index_reason === "thin"
            ? "Fewer than " + ((DATA && DATA.meta && DATA.meta.min_comps) || 5) + " usable comps in the window"
            : "No comps stored for this card yet") + '">' + esc(why) + "</span>";
    }
    return money(c.index_usd);
  }

  function cardRow(c, rank) {
    var open = !!state.open[c.card_id];
    var head =
      '<div class="mlb-card cards-card' + (open ? " is-open" : "") + '" style="--org-color:' +
        stripeFor(c) + '" data-cardopen="' + esc(c.card_id) + '" tabindex="0" role="button" ' +
        'aria-expanded="' + (open ? "true" : "false") + '">' +
        '<span class="mlb-rank">' + esc(rank) + "</span>" +
        '<span class="cards-ident">' +
          '<span class="mlb-name">' + teamLogo(c.org) + nameLink(c) + "</span>" +
          '<span class="mlb-sub">' + esc(c.org || "-") + " &middot; " + esc(c.set || "-") +
            " &middot; " + esc(c.grade || "-") + "</span>" +
        "</span>" +
        '<span class="mlb-metric"><span class="mlb-metric-label">eFV</span>' + efvCell(c) + "</span>" +
        '<span class="mlb-metric"><span class="mlb-metric-label">Index</span>' + indexCell(c) + "</span>" +
        '<span class="mlb-metric"><span class="mlb-metric-label">Trend</span>' + trendCell(c) + "</span>" +
        '<span class="mlb-metric"><span class="mlb-metric-label">Gap</span>' +
          (num(c.gap) === null ? "-" : (num(c.gap) > 0 ? "+" : "") + f1(c.gap)) + "</span>" +
        '<div class="mlb-tape"><div class="mlb-tape-inner">' +
          // The three phone-only chips carry the row-1 metrics down into the
          // scrolling tape, because the <=720px collapse drops the metric track
          // (34px rail + identity is all a 390px card can hold). CSS shows
          // exactly one of the two copies at any width, so nothing is duplicated
          // on screen and nothing is lost on a phone.
          '<div class="mlb-chip cards-chip-phone"><b>Index</b>' + indexCell(c) + "</div>" +
          '<div class="mlb-chip cards-chip-phone"><b>eFV</b>' + efvCell(c) + "</div>" +
          // Trend was the ONE row-1 metric with no phone twin: below 720px the
          // metric track is hidden and the only "Trend" left in the tape was the
          // sparkline, so the percentage simply vanished on a phone.
          '<div class="mlb-chip cards-chip-phone"><b>Trend</b>' + trendCell(c) + "</div>" +
          '<div class="mlb-chip cards-chip-phone"><b>Gap</b>' +
            (num(c.gap) === null ? "-" : (num(c.gap) > 0 ? "+" : "") + f1(c.gap)) + "</div>" +
          '<div class="mlb-chip"><b>Signal</b>' + signalChip(c) + "</div>" +
          '<div class="mlb-chip"><b>Talent pct</b>' + (num(c.talent_pct) === null ? "-" : f1(c.talent_pct)) + "</div>" +
          '<div class="mlb-chip"><b>Price pct</b>' + (num(c.market_pct) === null ? "-" : f1(c.market_pct)) + "</div>" +
          '<div class="mlb-chip"><b>Comps in window</b>' + esc(c.index_n == null ? "0" : c.index_n) + "</div>" +
          '<div class="mlb-chip"><b>Prior index</b>' + (c.prior_index_usd == null ? "-" : money(c.prior_index_usd)) + "</div>" +
          // "History", not "Trend": the row-1 metric track and the phone chip
          // both already carry a cell labelled Trend, and this one is the
          // sparkline of published index points, which is what the detail
          // drawer calls "Index history" too.
          '<div class="mlb-chip"><b>History</b>' + sparkline(c.history, { width: 110, height: 22 }) + "</div>" +
        "</div></div>" +
      "</div>";
    return head + (open ? detailPanel(c) : "");
  }

  function detailPanel(c) {
    var win = c.index_window || [];
    var link = c.mlbam ? hrefFor(c.mlbam) : null;
    return '<div class="cards-detail" data-carddetail="' + esc(c.card_id) + '">' +
      '<div class="cards-detail-grid">' +
        '<div class="cards-detail-block">' +
          '<div class="cards-detail-h">Index history</div>' +
          sparkline(c.history, { width: 260, height: 60 }) +
          '<div class="cards-detail-sub">' + esc(c.history && c.history.length ? c.history.length : 0) +
            " published point" + ((c.history || []).length === 1 ? "" : "s") +
            ". History starts the day this module first exported, not the day the card printed." +
          "</div>" +
        "</div>" +
        '<div class="cards-detail-block">' +
          '<div class="cards-detail-h">This index</div>' +
          '<dl class="cards-dl">' +
            "<dt>Card</dt><dd>" + esc(c.set || "-") + (c.parallel ? " &middot; " + esc(c.parallel) : "") + "</dd>" +
            "<dt>Grade basis</dt><dd>" + esc(c.grade || "-") + "</dd>" +
            "<dt>Window</dt><dd>" + esc(win[0] || "-") + " to " + esc(win[1] || "-") + "</dd>" +
            "<dt>Usable comps</dt><dd>" + esc(c.index_n == null ? 0 : c.index_n) + "</dd>" +
            "<dt>Comps on file</dt><dd>" + esc(c.comp_count_total == null ? 0 : c.comp_count_total) + "</dd>" +
          "</dl>" +
        "</div>" +
        '<div class="cards-detail-block">' +
          '<div class="cards-detail-h">Screen reading</div>' +
          "<p>" + esc(readingFor(c)) + "</p>" +
          '<div class="cards-detail-actions">' +
            (link ? '<a class="chip" href="' + esc(link) + '">Player page</a>' : "") +
            '<button type="button" class="chip" data-cardgfx="' + esc(c.card_id) + '">Generate GFX</button>' +
          "</div>" +
        "</div>" +
      "</div>" +
      '<div class="cards-detail-foot">A screen, not investment advice. The index is a derived ' +
        "statistic from public sold prices; individual sales are not republished.</div>" +
    "</div>";
  }

  function readingFor(c) {
    if (c.gap === null || c.gap === undefined) {
      return "No index yet, so there is no gap to read. The card is tracked and will price " +
             "once enough comps land in the window.";
    }
    var tier = c.tier === "mlb" ? "MLB cards" : "prospect cards";
    if (c.signal === "buy") {
      return "Ranks higher on talent than on price among " + tier + " on this watchlist. " +
             "That is the whole claim: a rank gap, not a price target.";
    }
    if (c.signal === "fade") {
      return "Prices above where the talent ranks among " + tier + " on this watchlist. " +
             "Hobby demand is not only performance, so read this as a question, not a verdict.";
    }
    return "Talent rank and price rank sit close together among " + tier + " on this watchlist.";
  }

  // ---- boards ---------------------------------------------------------------
  function boardHead(cols) {
    return '<div class="mlb-card-head cards-head">' + cols.map(function (c) {
      return "<span>" + esc(c) + "</span>";
    }).join("") + "</div>";
  }
  var HEAD_COLS = ["#", "Card", "eFV", "Index", "Trend", "Gap"];

  // An empty board has TWO different causes and they need two different
  // sentences. Saying "no card has a priced index yet" to a reader who just
  // typed a name that matches nothing is false, and the reverse - telling a
  // reader to "run the ingest" - is an instruction to the site operator printed
  // on a public page. filtering() answers which case we are in.
  //
  // The pre-fix copy on the watchlist was the worst of both: filter to zero
  // matches and it read "The watchlist is empty. Regenerate
  // data/card_watchlist.json", on a board that was showing 40 cards a keystroke
  // earlier.
  function filtering() {
    return state.tier !== "ALL" || !!(state.query || "").trim();
  }
  function noMatchMsg() {
    var bits = [];
    if ((state.query || "").trim()) bits.push('"' + (state.query || "").trim() + '"');
    if (state.tier !== "ALL") bits.push(state.tier === "mlb" ? "MLB cards" : "prospect cards");
    return "No tracked card matches " + (bits.join(" in ") || "this filter") +
           ". Clear the filter to see the whole board.";
  }
  function renderList(rows, emptyMsg) {
    if (!rows.length) {
      return '<div class="mlbstats-empty">' + esc(filtering() ? noMatchMsg() : emptyMsg) + "</div>";
    }
    return boardHead(HEAD_COLS) + '<div class="mlb-card-list cards-list">' +
      rows.map(function (c, i) { return cardRow(c, i + 1); }).join("") + "</div>";
  }

  function renderBuy() {
    var rows = filtered().filter(function (c) { return c.gap !== null && c.gap !== undefined; })
                         .sort(byDesc("gap"));
    return screenBanner() + filterBar(rows.length) +
      '<p class="mlbstats-note">Ranked by the gap between where the player sits on talent and ' +
      'where the card sits on price, inside its own tier. Cards with no index are in Watchlist.</p>' +
      renderList(rows, "No card carries a priced index yet, so there is no gap to rank. The screen " +
                       "fills in as sold comps land in the window; every tracked card is in Watchlist " +
                       "in the meantime.");
  }

  function renderMovers() {
    var rows = filtered().filter(function (c) { return c.trend_pct !== null && c.trend_pct !== undefined; })
                         .sort(absDesc("trend_pct"));
    return screenBanner() + filterBar(rows.length) +
      '<p class="mlbstats-note">Biggest index change against the prior window. A mover needs ' +
      'both windows priced, so a card can be tracked and still not appear here.</p>' +
      renderList(rows, "No card has two priced windows yet. Movers fill in as history accumulates.");
  }

  function renderWatchlist() {
    var rows = filtered().slice().sort(byEfvThenName);
    var m = (DATA && DATA.meta) || {};
    return screenBanner() + filterBar(rows.length) +
      '<p class="mlbstats-note">Every tracked card, priced or not. ' + esc(m.n_priced || 0) +
      " of " + esc(m.n_cards || 0) + " carry an index today.</p>" +
      renderList(rows, "No card is being tracked yet. The watchlist is curated, so this board is " +
                       "empty until cards are added to it.");
  }

  function renderMethod() {
    var m = (DATA && DATA.method) || {};
    var d = (DATA && DATA.disclaimer) || {};
    var gf = m.grade_factors || {};
    var rows = Object.keys(gf).map(function (k) {
      return "<tr><td>" + esc(k) + "</td><td>" + esc(gf[k]) + "</td></tr>";
    }).join("");
    return '<div class="cards-method">' +
      "<h2>What the Card Index is</h2>" +
      "<p>" + esc(m.index || "A grade-mix adjusted trimmed median of sold comps in a rolling window.") + "</p>" +
      "<p>Prices are published on a coarse grid (" +
        esc(m.publish_grid || "nearest dollar, then nearest five, then nearest twenty-five") +
        "). That is deliberate. A median of an odd sample can land exactly on one observed sale, " +
        "and this module publishes a statistic about a market, not a quotation of somebody's sale.</p>" +
      "<h2>Grade factors</h2>" +
      "<p>Every comp is moved onto the card's own grade bucket before the median. A comp whose " +
        "grade is not in this table is dropped, never guessed at.</p>" +
      '<div class="mlbstats-scroll"><table class="mlbstats-table"><thead><tr><th>Grade</th>' +
        "<th>Factor vs PSA 10</th></tr></thead><tbody>" + rows + "</tbody></table></div>" +
      "<h2>The screen</h2>" +
      "<p>" + esc(m.talent || "") + "</p>" +
      "<p>" + esc(m.gap || "") + "</p>" +
      "<p>Signal bands sit at " + esc((m.bands && m.bands.buy) || 20) + " and " +
        esc((m.bands && m.bands.fade) || -20) + " points of gap. " +
        esc((m.bands && m.bands.note) || "") + "</p>" +
      "<h2>Sources</h2>" +
      "<p>" + esc(m.sources || "") + "</p>" +
      "<h2>What this is not</h2>" +
      "<ul><li>" + esc(d.screen || "") + "</li><li>" + esc(d.derived || "") +
        "</li><li>" + esc(d.collectible || "") + "</li></ul>" +
      "</div>";
  }

  function screenBanner() {
    return '<div class="cards-screen-banner">' +
      '<span class="cards-screen-tag">Screen</span>' +
      "<span>Derived index values only. Not investment advice, and not a backtested signal: " +
      "there is no price-history backtest yet, so every call on this page is a screen. " +
      "Individual sales and listings are not republished.</span></div>";
  }

  // rowCount gates the board GFX button. On a zero-comp export the Buy Screen
  // has no rows, and "Generate GFX" was still offered: it opened the export
  // dialog on a board with a title, a legend, a column rule and NOTHING under
  // it, and the Download PNG button in that dialog works. A blank shareable
  // graphic with the site's name on it is worse than no button, so the button
  // is only emitted when there is something to draw.
  function filterBar(rowCount) {
    var tiers = ["ALL", "prospect", "mlb"];
    return '<div class="cards-filters">' +
      '<div class="cards-tiers">' + tiers.map(function (t) {
        return '<button type="button" class="chip' + (state.tier === t ? " active" : "") +
          '" data-cardtier="' + esc(t) + '">' +
          esc(t === "ALL" ? "All cards" : (t === "mlb" ? "MLB" : "Prospects")) + "</button>";
      }).join("") + "</div>" +
      '<input id="cards-search" class="cards-search" type="search" placeholder="Filter by player, org or set" ' +
        'value="' + esc(state.query) + '" aria-label="Filter cards">' +
      ((window.EEPHUS_GFX && rowCount)
        ? '<button type="button" class="chip" id="cards-board-gfx">Generate GFX</button>' : "") +
      "</div>";
  }

  // ---- GFX ------------------------------------------------------------------
  // The exported board follows the board you are LOOKING AT. It used to always
  // rebuild the Buy Screen rows: from Watchlist or Movers, "Generate GFX" quietly
  // handed you a different board than the one on screen, and on a zero-comp
  // export that different board was empty.
  function sectionRows() {
    if (section === "movers") {
      return { rows: filtered().filter(function (c) { return num(c.trend_pct) !== null; })
                               .sort(absDesc("trend_pct")),
               title: "Card Market · Movers", file: "cards-movers",
               noun: "cards with two priced windows" };
    }
    if (section === "watchlist") {
      return { rows: filtered().slice().sort(byEfvThenName),
               title: "Card Market · Watchlist", file: "cards-watchlist",
               noun: "tracked cards" };
    }
    return { rows: filtered().filter(function (c) { return c.gap !== null && c.gap !== undefined; })
                             .sort(byDesc("gap")),
             title: "Card Market · Buy Screen", file: "cards-buy-screen",
             noun: "priced cards" };
  }
  function boardSpec() {
    var cur = sectionRows();
    var rows = cur.rows;
    var brows = rows.map(function (c, i) {
      return { cells: [
        { t: i + 1 },
        // KEEP THE SUB SHORT. The board renderer in eephus-gfx.js draws a
        // cell's `sub` at its natural width with no fitTxt() clamp, so anything
        // long runs straight over the next column: "WSH Topps Chrome Rookie
        // Refractor" collided with the eFV number on every row of the 16:9
        // two-column layout. Org plus grade identifies the row and fits; the
        // set name lives on the page, which is where the link points.
        { t: c.name || c.player_key,
          sub: [c.org, c.grade].filter(Boolean).join(" ") },
        { t: fEfv(c.efv) },
        { t: money(c.index_usd), c: "accent" },
        { t: pct(c.trend_pct, true), c: num(c.trend_pct) > 0 ? "pos" : (num(c.trend_pct) < 0 ? "neg" : "muted") },
        { t: (num(c.gap) > 0 ? "+" : "") + f1(c.gap) },
      ] };
    });
    return {
      kind: "board", module: "Card Market", accentToken: "--accent-gold",
      title: cur.title,
      subtitle: rows.length + " " + cur.noun + " · eephus Card Index, derived from public sold prices",
      url: "eephus.io/cards", filenameBase: cur.file,
      caption: "a screen, not investment advice · index values are derived statistics, raw comps are not republished",
      board: { defaultCount: 25, counts: [10, 25, 50],
        legend: "Index = grade-adjusted trimmed median · Gap = talent percentile minus price percentile",
        // The identity column carries a name AND a sub on one baseline, so it
        // needs more of the panel than four short numeric cells do. 0.34 was
        // not enough for either half of the two-column 16:9 layout.
        columns: [
          { label: "#", frac: 0.05 },
          { label: "Card", frac: 0.47 },
          { label: "eFV", frac: 0.10 },
          { label: "Index", frac: 0.14 },
          { label: "Trend", frac: 0.12, wideOnly: true },
          { label: "Gap", frac: 0.12 },
        ], rows: brows },
    };
  }

  function cardSpec(c) {
    return {
      kind: "board", module: "Card Market", accentToken: "--accent-gold",
      title: (c.name || c.player_key) + " · Card Index",
      subtitle: [c.org, c.set, c.grade].filter(Boolean).join(" · "),
      url: "eephus.io/cards", filenameBase: "cards-" + String(c.card_id).replace(/\|/g, "-"),
      caption: "a screen, not investment advice · derived index, raw comps not republished",
      board: { defaultCount: 10, counts: [10],
        legend: "eephus Card Index · grade-adjusted trimmed median of public sold prices",
        columns: [{ label: "Measure", frac: 0.55 }, { label: "Value", frac: 0.45 }],
        rows: [
          { cells: [{ t: "Card Index" }, { t: money(c.index_usd), c: "accent" }] },
          { cells: [{ t: "Prior window" }, { t: money(c.prior_index_usd) }] },
          { cells: [{ t: "Trend" }, { t: pct(c.trend_pct, true),
                                      c: num(c.trend_pct) > 0 ? "pos" : (num(c.trend_pct) < 0 ? "neg" : "muted") }] },
          { cells: [{ t: "eFV" }, { t: fEfv(c.efv) }] },
          { cells: [{ t: "Talent percentile" }, { t: f1(c.talent_pct) }] },
          { cells: [{ t: "Price percentile" }, { t: f1(c.market_pct) }] },
          { cells: [{ t: "Gap" }, { t: (num(c.gap) > 0 ? "+" : "") + f1(c.gap) }] },
          { cells: [{ t: "Comps in window" }, { t: String(c.index_n == null ? 0 : c.index_n) }] },
        ] },
    };
  }

  // ---- render ---------------------------------------------------------------
  function render() {
    var root = el("cards-app-root");
    if (!root) return;
    if (LOAD_ERROR || (DATA && !(DATA.cards || []).length)) {
      root.innerHTML = emptyStateHTML();
      var rb = el("cards-retry");
      if (rb) rb.addEventListener("click", load);
      return;
    }
    if (!DATA) {
      root.innerHTML = '<div class="state-message is-loading"><div class="state-message-title">' +
        "Loading the card market</div></div>";
      return;
    }
    root.innerHTML = section === "method" ? renderMethod()
      : section === "movers" ? renderMovers()
      : section === "watchlist" ? renderWatchlist()
      : renderBuy();
    bind(root);
    var banner = el("cards-banner");
    if (banner) {
      var m = DATA.meta || {};
      banner.innerHTML = '<div class="cards-meta">' +
        esc(m.n_cards || 0) + " cards tracked · " + esc(m.n_priced || 0) + " priced · as of " +
        esc(DATA.as_of || "-") + (DATA.screen ? ' · <b class="cards-screen-word">screen</b>' : "") +
        "</div>";
    }
  }

  // TWO different failures, two different headlines. "Card Market is not built
  // yet" was printed for BOTH, and it is simply false in the LOAD_ERROR case:
  // a reader on a flaky connection, or hitting a five-minute CDN blip, was told
  // the module does not exist. The reader-facing sentence comes first and the
  // file and script names drop to a muted diagnostic line, because this card
  // renders on a public page and a stranger should not be handed a build
  // instruction as the main text.
  function emptyStateHTML() {
    var title = LOAD_ERROR ? "The card market did not load" : "No cards are being tracked yet";
    var why = LOAD_ERROR
      ? "The board could not fetch its data. That is usually the connection rather than the " +
        "module: try again, and if it keeps failing the export has not published."
      : "The payload is here but carries no cards. Until a card is on the watchlist there is " +
        "nothing to price, and an empty board is the honest thing to show.";
    return '<div class="state-message is-error">' +
      '<div class="state-message-title">' + esc(title) + "</div>" +
      '<div class="state-message-body"><p>' + esc(why) + "</p>" +
      '<p><button type="button" class="chip" id="cards-retry">Retry</button></p>' +
      '<p class="cards-meta">Source: <code>/data/card_market.json</code>, written by ' +
      "<code>card_market_export.py</code> from <code>data/card_watchlist.json</code>.</p>" +
      "</div></div>";
  }

  function bind(root) {
    Array.prototype.forEach.call(root.querySelectorAll("[data-cardtier]"), function (b) {
      b.addEventListener("click", function () {
        state.tier = b.getAttribute("data-cardtier");
        render();
      });
    });
    var q = root.querySelector("#cards-search");
    if (q) q.addEventListener("input", function () {
      state.query = q.value;
      render();
      var again = el("cards-search");
      if (again) { again.focus(); again.setSelectionRange(again.value.length, again.value.length); }
    });
    Array.prototype.forEach.call(root.querySelectorAll("[data-cardopen]"), function (row) {
      var id = row.getAttribute("data-cardopen");
      var toggle = function (e) {
        // let the player link and the inner buttons do their own job
        if (e && e.target && e.target.closest && e.target.closest("a,button")) return;
        if (state.open[id]) delete state.open[id]; else state.open[id] = 1;
        render();
        var again = document.querySelector('[data-cardopen="' + id + '"]');
        if (again) again.focus();
      };
      row.addEventListener("click", toggle);
      row.addEventListener("keydown", function (e) {
        if (e.key !== "Enter" && e.key !== " ") return;
        e.preventDefault();
        toggle(null);
      });
    });
    Array.prototype.forEach.call(root.querySelectorAll("[data-cardgfx]"), function (b) {
      b.addEventListener("click", function (e) {
        e.stopPropagation();
        var id = b.getAttribute("data-cardgfx");
        var c = allCards().filter(function (x) { return x.card_id === id; })[0];
        if (c && window.EEPHUS_GFX) EEPHUS_GFX.open(cardSpec(c));
      });
    });
    var g = root.querySelector("#cards-board-gfx");
    if (g) g.addEventListener("click", function () {
      if (window.EEPHUS_GFX) EEPHUS_GFX.open(boardSpec());
    });
  }

  // ---- section nav / boot ---------------------------------------------------
  // THE TAB WIRING IS DELIBERATELY TOLERANT, and that is not defensive
  // programming for its own sake. The page shell emits its buttons as
  // data-cardSSection="screen|movers|watchlist|method" while this module was
  // written against data-cardSection="buy|...". Rendered for the first time in
  // a real browser on 2026-08-05, that one-letter attribute name plus the
  // screen/buy value split meant querySelectorAll matched NOTHING: three of the
  // four boards, including Watchlist (the only populated board in a zero-comp
  // run) and Method, were unreachable and no error was thrown to say so.
  //
  // Accepting BOTH attribute spellings and aliasing "screen" -> "buy" fixes it
  // from the asset side, with no rebuild, and stays correct if the shell is
  // later normalised to the singular name.
  var SECTION_NODES = "[data-cardsection],[data-cardssection]";
  var SECTION_ALIAS = { screen: "buy", buy: "buy" };
  function sectionOf(node) {
    var raw = node.getAttribute("data-cardsection") || node.getAttribute("data-cardssection") || "";
    return SECTION_ALIAS[raw] || raw;
  }
  function setSection(s) {
    s = SECTION_ALIAS[s] || s;
    if (!SECTIONS[s]) return;
    section = s;
    Array.prototype.forEach.call(document.querySelectorAll(SECTION_NODES), function (x) {
      var on = sectionOf(x) === s;
      x.classList.toggle("active", on);
      x.setAttribute("aria-selected", on ? "true" : "false");
    });
  }
  function bindSectionNav() {
    Array.prototype.forEach.call(document.querySelectorAll(SECTION_NODES), function (b) {
      b.addEventListener("click", function () {
        setSection(sectionOf(b));
        try { history.replaceState(null, "", "#" + section); } catch (e) { /* file:// */ }
        render();
      });
    });
  }
  function readHash() {
    var m = /^#(buy|screen|movers|watchlist|method)/.exec(location.hash || "");
    if (m) setSection(m[1]);
  }
  function loadLinks() {
    fetch("/data/player_links.json", { cache: "no-cache" })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (j) { LINKS = j; if (DATA) render(); })
      .catch(function () { LINKS = null; });
  }
  function load() {
    LOAD_ERROR = false;
    fetch(DATA_URL, { cache: "no-cache" })
      .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
      .then(function (j) { DATA = j; render(); })
      .catch(function () { DATA = null; LOAD_ERROR = true; render(); });
  }
  // history.replaceState does not fire hashchange, so this only ever sees a hash
  // somebody else wrote: a deep link followed from the nav or another page, or a
  // pasted /cards/#method. Same shape as redraft.js / fantasy.js / dfs.js, which
  // all carry this and which cards.js was the only module missing.
  function onHashChange() {
    var before = section;
    readHash();
    if (section !== before) render();
  }
  function init() {
    bindSectionNav();
    readHash();
    render();
    load();
    loadLinks();
    window.addEventListener("hashchange", onHashChange);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
