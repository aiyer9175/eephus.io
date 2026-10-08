/* Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
 * Unauthorized copying of this file, via any medium is strictly prohibited
 * Proprietary and confidential
 * Written by Noah J. Dengler (@ARKNDJL), 2026
 *
 * /arbitration/ - the Arbitration Predictor client.
 *
 * Three sections here; the fourth (Model) is server-rendered so the
 * accountability surface is complete with JavaScript off.
 *
 * The scoped stylesheet follows the accountability.js pattern: tokens only,
 * zero literal colours, and a comment justifying each token choice. site.css
 * belongs to another lane.
 */
(function () {
  "use strict";

  var BOARD_URL = "/data/arbitration.json";
  var HIST_URL = "/data/arb_history.json";
  var DASH = " - ";

  /* Flag bits, mirrored from arb_export.py. */
  var F_SERVICE_EST = 1, F_CLASS_EST = 2, F_NO_SALARY = 4,
      F_CARRY_FWD = 8, F_PRORATED = 16;

  var board = null, hist = null;
  var boardErr = false, histErr = false;
  var filters = { cls: "all", team: "all", flag: null };
  // #teams&team=CODE narrows the club view to one club (the Franchise page
  // links in with it, 2026-09-23). Anchored to a separator on the mlbstats
  // idiom; trusted only once the board carries that club.
  var TEAM_NARROW_RE = /(?:^#|[#&])team=([A-Z]{2,3})\b/;
  var teamNarrow = "";
  var sort = { key: "tot", dir: -1 };
  // Census X06-05 (2026-09-25): the board was pinned to this one order with no
  // name search across 853 rows. Every head but the rank now sorts; "next" is
  // the first remaining rung's dollars. The first click on a head takes its
  // natural direction (names A to Z, money high to low).
  var SORT_FIRST = { n: 1, t: 1, c: 1, yl: -1, next: -1, tot: -1 };
  var SORT_DEFAULT = { key: "tot", dir: -1 };
  var SORT_RE = /(?:^#|[#&])sort=(n|t|c|yl|next|tot)\.(a|d)\b/;
  var query = "";
  // THE BOARD SHOWS 100 ROWS AT A TIME (QCLP04, 2026-10-02). All 882 rows and
  // their logos were 16,181 elements and 1.5 to 1.8 s of row paint; /hof/ and
  // the trade board window the same way. Show more adds 100, Show all paints
  // the rest (the CSV takes what is on screen, so Show all is its full path).
  // A filter, search or club change starts the window over; a sort keeps it.
  var PAGE = 100;
  var shown = PAGE;
  // History season filter. "all" shows every row the artifact carries; the
  // table windows at PAGE rows like the board, and Show all reaches every row.
  var histSeason = "all";
  var histShown = PAGE;

  /* ---------------------------------------------------------------- css */

  var css = document.createElement("style");
  css.textContent = [
    /* NO BORDER-RADIUS ANYWHERE. site.css sets a global
       `*,*::before,*::after{border-radius:0!important}` and this sheet is
       injected after it, so a radius written here would be dead code that
       still reads like intent. */

    /* The caveat bar is a caution rail, not a card, so it borrows the
       .card::before navy spine recoloured to --accent-orange: the token this
       site already spends on "early", never on "defective". */
    ".arb-app .arb-caveatbar{border:1px solid var(--border);border-left:5px solid var(--accent-orange);background:var(--bg-secondary);padding:9px 12px;margin:10px 0 14px}",
    ".arb-app .arb-caveatbar h2{font:700 10px/1.4 var(--font-retro-mono);letter-spacing:.12em;text-transform:uppercase;color:var(--accent-orange);margin:0 0 6px}",
    ".arb-app .arb-caveatbar ul{margin:0;padding-left:16px}",
    ".arb-app .arb-caveatbar li{font-size:12px;line-height:1.6;color:var(--text-secondary);margin:0 0 3px}",
    ".arb-app .arb-caveatn{font-family:var(--font-retro-mono);font-size:10px;color:var(--text-tertiary);margin-left:4px}",

    /* THE LADDER STRIP. Fixed 62px steps rather than content width, so the
       strips column-align down the whole board and a reader can scan "who has
       three years left" without reading a single number. That vertical
       alignment is the entire point of the component; content-width cells
       would destroy it. */
    ".arb-app .arb-ladder{display:grid;grid-auto-flow:column;gap:2px;justify-content:start}",
    ".arb-app .arb-step{display:block;width:62px;padding:2px 4px;text-align:center;border:1px solid var(--border-light)}",
    ".arb-app .arb-step i{display:block;font:700 8px/1.4 var(--font-retro-mono);letter-spacing:.06em;text-transform:uppercase;color:var(--text-tertiary);font-style:normal}",
    ".arb-app .arb-step b{display:block;font:700 11px/1.3 var(--font-retro-mono);color:var(--text-primary)}",
    /* SHAPE, NOT COLOUR, carries every distinction on this strip, so it
       survives a greyscale print. */
    ".arb-app .arb-step--min{border-style:dotted}",
    ".arb-app .arb-step--min b{color:var(--text-tertiary);font-weight:400}",
    ".arb-app .arb-step--est{border-color:var(--accent-orange)}",
    ".arb-app .arb-step--carry{border-top:2px solid var(--accent-orange)}",
    /* The free-agency bookend is what turns three numbers into a story with an
       end. Gold is the terminal accent and it is used exactly once here. */
    ".arb-app .arb-step--fa{border-color:var(--accent-gold);background:var(--bg-tertiary)}",
    ".arb-app .arb-step--fa i{color:var(--text-gold)}",

    /* The two residuals. A 3px rule is a newspaper column rule: whitespace
       reads as layout, a rule reads as a boundary. --accent-navy is the
       institutional hue (it is the header band) and the market residual is a
       claim about the SYSTEM; --accent-cyan is the computed hue and the value
       residual is the computed one. The SIGN rides --up/--down on the number
       itself, a separate channel, so hue answers "which question" and sign
       answers "which direction" without either overwriting the other. */
    ".arb-app .arb-gs{border-left:3px solid var(--border)}",
    ".arb-app th.arb-gs{border-left-color:var(--accent-navy)}",
    ".arb-app .arb-ou{font-family:var(--font-retro-mono);font-weight:700}",
    ".arb-app .arb-oubar{display:block;height:7px;margin-top:2px;background:var(--accent-cyan)}",
    ".arb-app .arb-pos{color:var(--up)}",
    ".arb-app .arb-neg{color:var(--down)}",
    ".arb-app th small{display:block;font:400 8px/1.3 var(--font-retro);letter-spacing:0;text-transform:none;color:var(--text-tertiary)}",

    ".arb-app .arb-flag{display:inline-block;font:700 8px/1.4 var(--font-retro-mono);letter-spacing:.08em;text-transform:uppercase;padding:1px 4px;border:1px solid var(--border);color:var(--text-tertiary);white-space:nowrap}",
    ".arb-app .arb-flag--est{color:var(--accent-orange);border-color:var(--accent-orange)}",
    ".arb-app .arb-scorecard{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:10px;margin:0 0 16px}",
    ".arb-app .arb-tile{border:1px solid var(--border);border-top-width:3px;background:var(--bg-secondary);padding:12px 14px}",
    ".arb-app .arb-tile--green{border-top-color:var(--accent-green)}",
    ".arb-app .arb-tile--orange{border-top-color:var(--accent-orange)}",
    ".arb-app .arb-tile--red{border-top-color:var(--accent-red)}",
    ".arb-app .arb-tile--navy{border-top-color:var(--accent-navy)}",
    ".arb-app .arb-tilen{font:700 26px/1 var(--font-retro-mono);color:var(--text-primary)}",
    ".arb-app .arb-tilelab{font:700 10px/1.4 var(--font-retro-mono);letter-spacing:.1em;text-transform:uppercase;color:var(--text-tertiary);margin:8px 0 0}",
    ".arb-app .arb-tiledef{font-size:11px;line-height:1.5;color:var(--text-secondary);margin:5px 0 0}",
    ".arb-app .arb-note{margin:10px 0}",
    ".arb-app .arb-note p,.arb-app .arb-note li{font-size:12px;line-height:1.6;color:var(--text-secondary)}",
    /* The History count line reads as a caption under the season chips. */
    ".arb-app .arb-histcount{font-size:12px;color:var(--text-secondary);margin:4px 0 8px}",
    ".arb-app .arb-row{border:1px solid var(--border);background:var(--bg-secondary);margin:0 0 6px;padding:8px 12px}",
    ".arb-app .arb-sum{cursor:pointer;font:700 12px/1.5 var(--font-retro-mono)}",
    ".arb-app .arb-vd{display:inline-block;font:700 9px/1.4 var(--font-retro-mono);letter-spacing:.1em;padding:1px 5px;border:1px solid var(--border);margin-right:6px}",
    ".arb-app .arb-vd--pass{color:var(--accent-green);border-color:var(--accent-green)}",
    ".arb-app .arb-vd--null{color:var(--accent-orange);border-color:var(--accent-orange)}",
    ".arb-app .arb-row dt{font:700 10px/1.5 var(--font-retro-mono);text-transform:uppercase;letter-spacing:.08em;color:var(--text-tertiary);margin-top:6px}",
    ".arb-app .arb-row dd{margin:0;font-size:12px;color:var(--text-primary)}",
    ".arb-app .arb-losses li{font-size:12px;line-height:1.6;color:var(--text-secondary);margin:0 0 8px}",

    /* THE CLUB FILTER AND THE TWO STATE BUTTONS WERE THE ONLY UNSTYLED
       CONTROLS ON THE PAGE (owner report 2026-08-12: the org button "isn't on
       theme and looks very out of place").

       A bare <select> renders in the platform UI font with the platform's own
       chrome, so it sat beside pixel-font chips looking like a piece of the
       browser rather than a piece of the site. Same for the two native
       <button>s, which had no class at all and so picked up the UA's grey
       bevel.

       The fix joins the families that already exist rather than inventing a
       parallel dialect: these declarations are copied from
       `.mlbstats-bar input, .mlbstats-bar select` in site.css, which is the
       select treatment every /mlbstats/ board already uses. The arb filter bar
       is not inside a .mlbstats-bar, which is the only reason it did not
       inherit them. Buttons become .chip and pick up `.fa-app button.chip`
       from site.css, which is what the class chips beside them already are.
       No colour literals, no radius (the global rule zeroes it anyway). */
    ".arb-app .filter-bar select,.arb-app .arb-findbar select{font-family:var(--font-retro-mono);font-size:12px;padding:6px 9px;background:var(--bg-secondary);color:var(--text-primary);border:1px solid var(--border)}",
    ".arb-app .filter-bar select:focus-visible,.arb-app .arb-findbar select:focus-visible{outline:2px solid var(--accent-gold);outline-offset:1px}",
    /* The name search and the club picker sit on a row of their own above
       the class chips: on a phone the chip bar is a sideways scroller, and a
       search at its far end would be off screen. The field takes the site's
       control dialect (site.css section 12 and the control-theme sweep) and the
       club select's box, so the two stand at one height: the
       --text-tertiary boundary that clears 3:1 on its fill, the cyan ring,
       and 16px under a coarse pointer so iOS does not zoom on focus. */
    ".arb-app .arb-findbar{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin:10px 0 6px}",
    ".arb-app .arb-findbar input[type=search]{font-family:var(--font-retro-mono);font-size:12px;padding:6px 9px;background:var(--bg-secondary);color:var(--text-primary);border:1px solid var(--text-tertiary);min-width:0;width:200px;max-width:100%;box-sizing:border-box}",
    ".arb-app .arb-findbar input[type=search]:hover{border-color:var(--text-secondary)}",
    ".arb-app .arb-findbar input[type=search]:focus-visible{outline:2px solid var(--accent-cyan);outline-offset:2px}",
    "@media (pointer:coarse){.arb-app .arb-findbar input[type=search]{font-size:16px;min-height:44px}}",
    /* Sortable heads: a native <button> inside a <th scope=col aria-sort>, the
       /fa/ board's pattern, so a screen reader hears the sort state and Enter
       and Space work with no key shim. The sorted head takes the gold rule. */
    ".arb-app .arb-sort{display:block;width:100%;margin:0;padding:0;border:0;background:none;color:inherit;font:inherit;letter-spacing:inherit;text-transform:inherit;text-align:inherit;cursor:pointer;white-space:nowrap}",
    ".arb-app .arb-sort:hover{color:var(--text-primary)}",
    ".arb-app .arb-sort:focus-visible{outline:2px solid var(--accent-cyan);outline-offset:2px}",
    ".arb-app .arb-sort-ind{display:inline-block;min-width:.9em;text-align:left}",
    ".arb-app th[aria-sort=ascending],.arb-app th[aria-sort=descending]{color:var(--text-primary);border-bottom:2px solid var(--accent-gold)}",

    /* Club logos ride the board's Club cell and the Team View rows. The mark
       is 17px and the cell is nowrap, so the row height does not move. */
    ".arb-app .arb-club{display:inline-flex;align-items:center;gap:5px;white-space:nowrap}",

    /* Text columns (player, club, class) read left like a newspaper agate
       line; money and counts stay right-aligned and tabular. A head that does
       not sort draws the default cursor: site.css gives every .mlbstats-table
       head a pointer, and on History and Team View nothing sorts (QCLA16). */
    ".arb-app .mlbstats-table th.arb-l,.arb-app .mlbstats-table td.arb-l{text-align:left}",
    ".arb-app .mlbstats-table th{cursor:default}",
    /* How this works: the method, folded under the table it explains. */
    ".arb-app .arb-how{margin:10px 0 0;border-top:1px solid var(--border-light);padding-top:4px}",
    ".arb-app .arb-how>summary{cursor:pointer;font-size:12px;color:var(--text-secondary)}",
    ".arb-app .arb-how p,.arb-app .arb-how li{font-size:12px;line-height:1.6;color:var(--text-secondary);max-width:90ch}",
    ".arb-app .arb-how ul{margin:6px 0;padding-left:16px}",
    ".arb-app .arb-lede{font-size:12px;line-height:1.6;color:var(--text-secondary);margin:6px 0 8px;max-width:90ch}",
    ".arb-app .arb-more{display:flex;flex-wrap:wrap;gap:6px;margin:8px 0 0}",
    ".arb-app .arb-related{margin:22px 0 0;padding-top:8px;border-top:1px solid var(--border);font-size:12px;color:var(--text-secondary)}",

    /* On a phone the question is "how many years, how much total". The
       per-year dollar is deferred into title=, not deleted. Logos come out of
       the Club column there: at 44px steps the ladder is already the widest
       thing on screen and a 17px mark per row costs more than it tells. */
    "@media (max-width:640px){.arb-app .arb-step{width:44px}.arb-app .arb-step b{display:none}.arb-app .arb-ladder{gap:1px}.arb-app th small{display:none}.arb-app .arb-club .eephus-teamlogo{display:none}" +
    /* 44px touch targets at phone width (QCLA16): the row's name and club
       links and the sort heads were 14 and 16px tall. */
    ".arb-app .mlbstats-table td a{display:inline-flex;align-items:center;min-height:44px}.arb-app .arb-sort{min-height:44px}}"
  ].join("");
  document.head.appendChild(css);

  /* ------------------------------------------------------------- helpers */

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  // The pixel state box (assets/eephus-state.js, final-pass plan 5.7 PX-12):
  // loading, empty, unmeasured or failed, around a message this file escapes.
  // The bare box is the fallback for a test harness that loads this file alone.
  function pxState(kind, msg, opts) {
    var S = typeof window !== "undefined" && window.EephusState;
    if (S) return S.html(kind, msg, opts);
    var cls = typeof opts === "string" ? opts : (opts && opts.cls) || "";
    return '<div class="px-state is-' + kind + (cls ? " " + cls : "") + '"' +
      (kind === "failed" ? ' role="alert"' : "") + '><div class="px-state-msg">' + msg + "</div></div>";
  }

  /* Two-magnitude money, sign BEFORE the $. Missing data is DASH, never a
     dash glyph. */
  function money(usd, dp) {
    var n = Number(usd);
    if (usd == null || !isFinite(n)) return DASH;
    var neg = n < 0, a = Math.abs(n);
    if (a >= 1e9) return (neg ? "-" : "") + "$" + (a / 1e9).toFixed(2) + "B";
    var m = a / 1e6;
    var d = dp == null ? (m >= 100 ? 0 : 1) : dp;
    if (m < 1) return (neg ? "-" : "") + "$" + Math.round(a / 1e3) + "K";
    return (neg ? "-" : "") + "$" + m.toFixed(d) + "M";
  }

  function signed(usd) {
    if (usd == null || !isFinite(Number(usd))) return DASH;
    return (Number(usd) > 0 ? "+" : "") + money(usd);
  }

  function el(id) { return document.getElementById(id); }

  /* Club cell: the ESPN mark plus the code, via the shared hub helper that
     /betting/, /mlbstats/ and /pal/ all use. build_arbitration already loads
     eephus-hub.js on this page; it was simply never called, so the board
     rendered bare three-letter codes while every sibling module showed a mark.
     Degrades to the plain code when the hub is absent or the club is unknown,
     and the <img> carries its own onerror removal. The mark is decorative
     (alt="") because the code follows it as text (QCLA16), and a club the
     hub knows links to its /franchise/ page through the hub's one club
     resolver (EEPHUS_HUB.clubHref, owner ask 9). A code the hub does not know
     keeps its text in a span marked data-club-nolink="unresolved". */
  function club(code, noLogo) {
    var t = String(code == null ? "" : code).trim();
    if (!t) return DASH;
    var hub = window.EEPHUS_HUB;
    var logo = (!noLogo && hub && typeof hub.teamLogo === "function") ? hub.teamLogo(t, null, { decorative: true }) : "";
    var c = (hub && typeof hub.club === "function") ? hub.club(t) : null;
    var href = (c && c.code && typeof hub.clubHref === "function") ? hub.clubHref(c.code) : "";
    if (href) {
      return '<a class="arb-club club-link" href="' + esc(href) + '" data-club="' + esc(c.code) + '" title="' +
        esc(c.name + ": franchise overview") + '">' + logo + esc(t) + "</a>";
    }
    return '<span class="arb-club"' + (hub && hub.club ? ' data-club-nolink="unresolved"' : "") + ">" + logo + esc(t) + "</span>";
  }

  /* A name's link: the exporter resolves it ("p:" a /projections/ key, "x:"
     a PROSPX slug), so the page no longer fetches the 1.9 MB identity map to
     link 882 names (QCLP04). */
  function hrefOf(tok) {
    var s = String(tok == null ? "" : tok);
    if (s.indexOf("p:") === 0 && s.length > 2) return "/projections/#player=" + encodeURIComponent(s.slice(2));
    if (s.indexOf("x:") === 0 && s.length > 2) return "/prospx/#player=" + encodeURIComponent(s.slice(2));
    return null;
  }
  function nameLink(name, tok) {
    var h = hrefOf(tok);
    return h ? '<a href="' + esc(h) + '">' + esc(name) + "</a>" : esc(name);
  }

  /* --------------------------------------------------------- caveat bar */

  /* Five caveats, each on FOUR surfaces: an inline marker, a filter chip with
     a live count, this bar, and the Model tab. The bar is OPEN by default -
     the inverse of the chart fold - because a chart the reader has not asked
     for should be closed and a caveat they have not asked for is exactly the
     one that has to be visible. */
  function caveats() {
    if (!board) return "";
    var rows = board.rows || [];
    var n = function (bit) {
      var c = 0;
      for (var i = 0; i < rows.length; i++) if ((rows[i].e || 0) & bit) c++;
      return c;
    };
    var items = [];
    /* THE CAVEAT THIS PAGE NEEDED (2026-09-17). The ladder runs as far as the
       published grid, and on more than half the board that grid ends on a
       pre-arbitration token, which states nothing about when arbitration - let
       alone club control - begins or ends. First in the list because it is the
       one a reader has to have before reading anything else on the page. */
    var preEnd = 0;
    for (var pi = 0; pi < rows.length; pi++) {
      var _l = rows[pi].l || [];
      if (_l.length && (_l[_l.length - 1][4] || "") === "PRE-ARB") preEnd++;
    }
    // COPY PASS 2026-10-03: every caveat kept, each in one line. The Arb 2+
    // multiplier line left this bar because the masthead states the same
    // verdict; the method is in How this works under the table.
    if (preEnd) items.push("Ladders end where the published grid ends (pre-arb for <b>" +
      preEnd + "</b> players), not where club control ends (see " +
      "<a href=\"/projections/\">projections</a>).");
    var est = n(F_SERVICE_EST);
    var cls = n(F_CLASS_EST);
    if (est) items.push("~ marks an arb year without published service time: <b>" + est + "</b> players" +
      (cls ? ", <b>" + cls + "</b> from the debut-year heuristic (the weakest source)." : "."));
    var carry = n(F_CARRY_FWD);
    var rules = board.rules || {};
    if (carry) items.push(esc(String(rules.carry_forward_from || 2027)) + "+ seasons assume the <span data-gl=\"cba_carry_forward\">CBA</span> survives its <b>" + esc(rules.expires || "2026-12-01") + "</b> expiry; no interval covers that.");
    items.push("Non-tenders are absent, so club totals <b>overstate</b> what is owed.");
    return '<div class="arb-caveatbar"><h2>Caveats</h2><ul><li>' +
           items.join("</li><li>") + "</li></ul></div>";
  }

  /* How this works, folded under the board: the pricing rule per rung and the
     sources, read off arb_export.py and arb_model.py. Nothing here is a claim
     about accuracy; the Model tab carries every measured verdict. */
  function boardHow() {
    return '<details class="arb-how"><summary>How this works</summary><ul>' +
      "<li>Ladder: each remaining season and its token (ARB 1 to 4, PRE-ARB) from the Spotrac club grids.</li>" +
      "<li>Arb 1: the <span data-gl=\"arb_award_model\">award model</span>, from the prior salary and " +
      "the platform season, the one before the award: its WAR (fWAR basis; projected when it is unplayed), " +
      "role, playing time and skill metrics (the latest observed season's when it is unplayed), plus age, " +
      "floored at the league minimum.</li>" +
      "<li>Arb 2 to 4: the rung before times the median observed raise for its step and prior-salary band, " +
      "never below a 20% cut or the league minimum. The Model tab says how this compares with the model.</li>" +
      "<li>Pre-arb: the league minimum by rule.</li>" +
      "<li>Each rung raises off the one before, so a later rung carries the earlier rung's error.</li>" +
      "<li>Total remaining = the sum of the ladder, pre-arb minimums included.</li>" +
      "</ul></details>";
  }

  /* ------------------------------------------------------------- ladder */

  function ladder(r) {
    var steps = r.l || [];
    var out = [], aria = [];
    for (var i = 0; i < steps.length; i++) {
      var s = steps[i];
      var yr = s[0], usd = s[1], tok = s[4] || "";
      var pre = tok === "PRE-ARB";
      var cls = "arb-step";
      if (pre) cls += " arb-step--min";
      if ((r.e || 0) & F_SERVICE_EST) cls += " arb-step--est";
      if (yr > 2026) cls += " arb-step--carry";
      var lab = pre ? "MIN" : tok.replace("ARB ", "A").replace(/\s*\(S2\)/, "*");
      var tick = "'" + String(yr).slice(2);
      out.push('<span class="' + cls + '"><i>' + esc(lab) + " " + tick +
               "</i><b>" + money(usd) + "</b></span>");
      aria.push(esc(tok) + ", " + yr + ", " + money(usd));
    }
    /* NO FREE-AGENCY BOOKEND. It was invented from whatever season Spotrac's
       grid happened to stop at, and 442 of 852 rows stop on a PRE-ARB token,
       which says nothing about when arbitration begins. The richer fix - run
       class closure here so the ladder shows the rungs /projections/ already
       computes - reopens decision D3 and grows the published `tot` by 467
       seasons across 245 rows, so the board keeps publishing the grid it was
       given and stops claiming an end it cannot derive. */
    if (steps.length) aria.push("Ladder as published; the control end is not shown on this board");
    return '<div class="arb-ladder" role="img" aria-label="' +
           esc(aria.join(". ")) + '">' + out.join("") + "</div>";
  }

  /* ------------------------------------------------- projections board */

  function classLabel(r) {
    var c = r.c;
    if (c == null) return DASH;
    if (c === 0) return "Pre-Arb";
    var s = "Arb " + c;
    if ((r.e || 0) & F_SERVICE_EST) s = "~" + s;
    return s;
  }

  function filtered() {
    var rows = (board && board.rows) || [];
    var q = fold(query).trim();
    return rows.filter(function (r) {
      if (filters.team !== "all" && r.t !== filters.team) return false;
      if (filters.cls !== "all" && String(r.c) !== filters.cls) return false;
      if (filters.flag && !((r.e || 0) & filters.flag)) return false;
      if (q && fold(r.n).indexOf(q) < 0) return false;
      return true;
    });
  }

  /* Case- and accent-blind, so "rodriguez" finds "Rodr\u00edguez". */
  function fold(s) {
    var t = String(s == null ? "" : s).toLowerCase();
    try { t = t.normalize("NFD").replace(/[\u0300-\u036f]/g, ""); } catch (e) { /* old engines */ }
    return t;
  }

  function sortVal(r, key) {
    if (key === "next") return r.l && r.l.length ? r.l[0][1] : null;
    if (key === "n") return fold(r.n);
    return r[key];
  }

  function sortHash() {
    if (sort.key === SORT_DEFAULT.key && sort.dir === SORT_DEFAULT.dir) return "";
    return "&sort=" + sort.key + "." + (sort.dir < 0 ? "d" : "a");
  }

  function renderBoard() {
    var root = el("arb-app-root");
    if (!root) return;
    if (boardErr) {
      root.innerHTML = pxState("failed", "Arbitration board did not load. Retry; the nightly build may be writing it." +
        ' <button type="button" class="chip" id="arb-retry">Retry</button>');
      var b = el("arb-retry");
      if (b) b.onclick = function () { boardErr = false; load(); };
      return;
    }
    if (!board) {
      root.innerHTML = pxState("loading", "Loading the arbitration board.");
      return;
    }
    if (!board.rows || !board.rows.length) {
      root.innerHTML = pxState("unmeasured", "Arbitration board not built yet on this deploy; the nightly build writes it.");
      return;
    }
    var teams = {};
    (board.rows || []).forEach(function (r) { if (r.t) teams[r.t] = 1; });
    // aria-pressed carries the chip state a sighted reader gets from .active.
    function pressed(on) { return '" aria-pressed="' + (on ? "true" : "false"); }
    var chips = [["all", "All"], ["1", "Arb 1"], ["2", "Arb 2"], ["3", "Arb 3"], ["0", "Pre-Arb"]]
      .map(function (c) {
        return '<button type="button" class="chip' + (filters.cls === c[0] ? " active" : "") +
               pressed(filters.cls === c[0]) + '" data-cls="' + c[0] + '">' + c[1] + "</button>";
      }).join("");
    var estN = (board.rows || []).filter(function (r) { return (r.e || 0) & F_SERVICE_EST; }).length;
    chips += '<button type="button" class="chip' + (filters.flag ? " active" : "") + pressed(!!filters.flag) +
             '" data-flag="1">Arb year estimated <span class="arb-caveatn">(' + estN + ")</span></button>";
    var opts = ['<option value="all">All clubs</option>'].concat(
      Object.keys(teams).sort().map(function (t) {
        return '<option value="' + esc(t) + '"' + (filters.team === t ? " selected" : "") + ">" + esc(t) + "</option>";
      })).join("");

    root.innerHTML = caveats() +
      '<div class="arb-findbar"><input type="search" id="arb-q" placeholder="Search players" ' +
      'aria-label="Search players by name" autocomplete="off" value="' + esc(query) + '">' +
      '<select id="arb-team" data-team-picker aria-label="Club">' + opts + "</select></div>" +
      '<div class="filter-bar">' + chips + "</div>" +
      '<p class="arb-histcount" id="arb-count" role="status"></p>' +
      '<div id="arb-board-table"></div>' + boardHow();

    root.querySelectorAll("[data-cls]").forEach(function (b) {
      b.onclick = function () { filters.cls = b.getAttribute("data-cls"); shown = PAGE; renderBoard(); };
    });
    root.querySelectorAll("[data-flag]").forEach(function (b) {
      b.onclick = function () { filters.flag = filters.flag ? null : F_SERVICE_EST; shown = PAGE; renderBoard(); };
    });
    var sel = el("arb-team");
    if (sel) sel.onchange = function () { filters.team = sel.value; shown = PAGE; renderBoard(); };
    // Typing re-paints the table only, so the field keeps its focus and caret.
    var qi = el("arb-q");
    if (qi) qi.oninput = function () { query = qi.value; shown = PAGE; renderTable(); };
    var tbl = el("arb-board-table");
    if (tbl) tbl.onclick = function (e) {
      var mb = e.target && e.target.closest ? e.target.closest("[data-amore]") : null;
      if (mb) {
        var all = mb.getAttribute("data-amore") === "all";
        var first = shown;
        shown = all ? Infinity : shown + PAGE;
        renderTable();
        // Focus lands on the first new row's name, so a keyboard reader
        // continues where the list grew instead of at the top of the page.
        var nr = tbl.querySelectorAll("tbody tr")[first];
        var na = nr && nr.querySelector("a");
        if (na) na.focus();
        return;
      }
      var b = e.target && e.target.closest ? e.target.closest("[data-asort]") : null;
      if (b) {
        var k = b.getAttribute("data-asort");
        sort = sort.key === k ? { key: k, dir: -sort.dir } : { key: k, dir: SORT_FIRST[k] || -1 };
        renderTable();
        var nb = tbl.querySelector('[data-asort="' + k + '"]');
        if (nb) nb.focus();
        try { history.replaceState(null, "", "#projections" + sortHash()); } catch (err) { /* hash is optional */ }
        return;
      }
      if (e.target && e.target.id === "arb-clear") {
        filters = { cls: "all", team: "all", flag: null };
        query = "";
        shown = PAGE;
        renderBoard();
      }
    };
    renderTable();
    wireGl(root);
  }

  function renderTable() {
    var box = el("arb-board-table");
    if (!box || !board) return;
    var all = (board.rows || []).length;
    var rows = filtered().slice();
    // Missing values sink to the bottom in either direction; ties fall back to
    // the total remaining, largest first.
    rows.sort(function (a, b) {
      var x = sortVal(a, sort.key), y = sortVal(b, sort.key);
      if (x == null && y == null) return (b.tot || 0) - (a.tot || 0);
      if (x == null) return 1;
      if (y == null) return -1;
      return (x > y ? 1 : x < y ? -1 : 0) * sort.dir || ((b.tot || 0) - (a.tot || 0));
    });
    var arrow = sort.dir < 0 ? "&#9662;" : "&#9652;";
    function th(key, label, title, small, left) {
      var on = sort.key === key;
      // The title rides the th, so the head keeps its definition (Ladder yrs
      // and Total remaining say what they are not) for any reader of the head.
      return '<th scope="col"' + (left ? ' class="arb-l"' : "") + ' aria-sort="' + (on ? (sort.dir < 0 ? "descending" : "ascending") : "none") +
        '" title="' + esc(title) + '" data-export-text="' + esc(label) + '"><button type="button" class="arb-sort" data-asort="' + key +
        '">' + label + '<span class="arb-sort-ind" aria-hidden="true">' +
        (on ? arrow : "") + "</span>" + (small ? "<small>" + small + "</small>" : "") + "</button></th>";
    }
    var head =
      '<tr><th scope="col" class="mlbstats-col-rank">#</th>' +
      th("n", "Player", "Sort by name", null, true) + th("t", "Club", "Sort by club", null, true) +
      th("c", "Class", "Sort by arbitration class", null, true) +
      th("yl", "Ladder yrs", "Seasons on the published grid. Not the number of club-control seasons remaining.") +
      th("next", "Remaining arbitration ladder", "Sort by the first remaining season's dollars", "sorts on the next rung", true) +
      th("tot", "Total remaining", "Sum of the seasons on the published grid, not of the club control window.") +
      "</tr>";
    var matched = rows.length;
    var win = rows.slice(0, shown);
    var body = win.map(function (r, i) {
      return '<tr><td class="mlbstats-col-rank">' + (i + 1) + "</td>" +
        '<td class="mlbstats-name arb-l">' + nameLink(r.n, r.h) + '</td><td class="arb-l">' + club(r.t) + "</td>" +
        '<td class="arb-l">' + esc(classLabel(r)) + "</td><td>" + (r.yl == null ? DASH : r.yl) + "</td>" +
        '<td class="arb-laddercell arb-l">' + ladder(r) + "</td>" +
        "<td>" + money(r.tot) + "</td></tr>";
    }).join("");
    var cnt = el("arb-count");
    if (cnt) {
      cnt.textContent = win.length === matched || matched === all
        ? "Showing " + win.length + " of " + all + " players."
        : "Showing " + win.length + " of " + matched + " matching players (" + all + " on the board).";
    }
    var left = matched - win.length;
    var more = left > 0
      ? '<div class="arb-more"><button type="button" class="chip" data-amore="page">Show ' +
        Math.min(PAGE, left) + " more</button>" +
        (left > PAGE ? '<button type="button" class="chip" data-amore="all">Show all ' + matched + "</button>" : "") +
        "</div>"
      : "";
    box.innerHTML = rows.length
      ? '<div class="mlbstats-scroll"><table class="mlbstats-table arb-table"><thead>' +
        head + "</thead><tbody>" + body + "</tbody></table></div>" + more
      : '<div class="mlbstats-empty">No players match these filters. ' +
        '<button type="button" class="chip" id="arb-clear">Clear filters</button></div>';
  }

  /* Glossary spans ([data-gl]) get their aria wiring from the shared runtime;
     the tooltip itself is delegated and works without this call. */
  function wireGl(node) {
    try { if (node && window.EEPHUS_GL && window.EEPHUS_GL.wire) window.EEPHUS_GL.wire(node); }
    catch (e) { /* the glossary is enrichment */ }
  }

  /* ------------------------------------------------------------ history */

  function renderHistory() {
    var root = el("arb-panel-history");
    if (!root) return;
    if (histErr) {
      root.innerHTML = pxState("failed", "Arbitration history did not load.");
      return;
    }
    if (!hist) {
      root.innerHTML = pxState("loading", "Loading arbitration history.");
      return;
    }
    var rows = hist.rows || [];
    if (!rows.length) {
      root.innerHTML = '<div class="mlbstats-empty">Arbitration history not built yet on this deploy; the nightly build writes it.</div>';
      return;
    }
    // COPY PASS 2026-10-03: the two-paragraph note became one lede line that
    // keeps both definitions, the never-combined rule and the misreading
    // guard; the basis and the marks moved into How this works.
    var note =
      '<p class="arb-lede"><b><span data-gl="arb_market_residual">vs Market</span></b>: actual minus ' +
      "this model. <b>vs Value</b>: actual minus WAR in dollars. Never combined. Negative vs Market: " +
      "the model expected more, not an underpaid player.</p>";
    var how =
      '<details class="arb-how"><summary>How this works</summary><ul>' +
      "<li>Every dollar column is nominal. Ours is the model's out-of-sample prediction, re-inflated by " +
      "the deflator its own fold fitted on earlier seasons.</li>" +
      "<li>vs Market = actual &minus; ours. It sums to about zero by construction.</li>" +
      "<li>vs Value = actual &minus; WAR &times; $/WAR for that season, WAR on the fWAR basis (the " +
      "arbitration model&rsquo;s spine). Arbitration pays below the open market, so it does not sum to zero.</li>" +
      "<li>MLBTR is the MLB Trade Rumors (Matt Swartz) projection published before settlement, where one exists.</li>" +
      "<li>&dagger; 2020, paid at 60/162. ~ the arb year is not from published service time.</li>" +
      "</ul></details>";

    var head = '<tr><th scope="col" class="mlbstats-col-rank">#</th><th scope="col">Season</th>' +
      '<th scope="col" class="arb-l">Player</th><th scope="col" class="arb-l">Club</th><th scope="col">Arb</th>' +
      '<th scope="col">Actual</th><th scope="col">Ours</th><th scope="col">MLBTR</th>' +
      '<th scope="col" class="arb-gs">vs Market<small>actual minus model</small></th>' +
      '<th scope="col">vs Value<small>actual minus WAR (fWAR basis) &times; $/WAR</small></th></tr>';

    // EVERY ROW RENDERS. This table used to print rows.slice(0, 400) of a
    // season-descending list with no count, so 372 of 772 rows were hidden,
    // including every 2023 row and 254 of the 282 MLBTR figures the Model tab
    // cites. A season filter narrows it instead, and the count line says how
    // many rows show and how many carry an MLBTR figure.
    var bySeason = {};
    rows.forEach(function (r) {
      var b = bySeason[r[0]] || (bySeason[r[0]] = { n: 0, sw: 0 });
      b.n++;
      if (r[7] != null) b.sw++;
    });
    var seasons = Object.keys(bySeason).sort().reverse();
    if (histSeason !== "all" && !bySeason[histSeason]) histSeason = "all";
    var vis = histSeason === "all" ? rows
      : rows.filter(function (r) { return String(r[0]) === histSeason; });
    var nSw = 0;
    vis.forEach(function (r) { if (r[7] != null) nSw++; });
    var chips = '<button type="button" class="chip' + (histSeason === "all" ? " active" : "") +
      '" aria-pressed="' + (histSeason === "all") + '" data-hseason="all">All seasons <span class="arb-caveatn">(' + rows.length + ")</span></button>" +
      seasons.map(function (y) {
        return '<button type="button" class="chip' + (histSeason === y ? " active" : "") +
          '" aria-pressed="' + (histSeason === y) + '" data-hseason="' + esc(y) + '">' + esc(y) +
          ' <span class="arb-caveatn">(' + bySeason[y].n + ")</span></button>";
      }).join("");
    var win = vis.slice(0, histShown);
    var countLine = '<p class="arb-histcount" role="status">' + (win.length === vis.length
      ? "Showing " + vis.length + " of " + rows.length + " settled seasons. " + nSw + " of them carry an MLBTR projection."
      : "Showing " + win.length + " of " + vis.length + (vis.length === rows.length ? "" : " matching (" + rows.length + " in all)") +
        " settled seasons (" + nSw + " with an MLBTR projection).") + "</p>";
    var left = vis.length - win.length;
    var more = left > 0
      ? '<div class="arb-more"><button type="button" class="chip" data-hmore="page">Show ' + Math.min(PAGE, left) +
        " more</button>" + (left > PAGE ? '<button type="button" class="chip" data-hmore="all">Show all ' +
        vis.length + "</button>" : "") + "</div>"
      : "";

    // The bar scale is the season filter's, so it does not move as the window grows.
    var maxOu = 1;
    vis.forEach(function (r) { if (r[9] != null) maxOu = Math.max(maxOu, Math.abs(r[9])); });

    var body = win.map(function (r, i) {
      var ouM = r[8], ouW = r[9];
      var bar = ouW == null ? "" :
        '<span class="arb-oubar" style="width:' +
        Math.round(40 * Math.abs(ouW) / maxOu) + 'px"></span>';
      return "<tr>" +
        '<td class="mlbstats-col-rank">' + (i + 1) + "</td>" +
        "<td>" + r[0] + ((r[11] || 0) & F_PRORATED ? " &dagger;" : "") + "</td>" +
        '<td class="mlbstats-name arb-l">' + nameLink(r[2], r[12]) + '</td><td class="arb-l">' + (r[3] ? club(r[3], true) : DASH) + "</td>" +
        "<td>" + ((r[11] || 0) & F_SERVICE_EST ? "~" : "") + "A" + r[4] + "</td>" +
        "<td>" + money(r[5]) + "</td><td>" + money(r[6]) + "</td><td>" + money(r[7]) + "</td>" +
        '<td class="arb-gs arb-ou ' + (ouM > 0 ? "arb-pos" : "arb-neg") + '">' + signed(ouM) + "</td>" +
        '<td class="arb-ou">' + signed(ouW) + bar + "</td>" +
        "</tr>";
    }).join("");

    root.innerHTML = note +
      '<div class="filter-bar">' + chips + "</div>" + countLine +
      '<div class="mlbstats-scroll"><table class="mlbstats-table arb-table"><thead>' +
      head + "</thead><tbody>" + body + "</tbody></table></div>" + more + how;
    root.querySelectorAll("[data-hseason]").forEach(function (b) {
      b.onclick = function () { histSeason = b.getAttribute("data-hseason"); histShown = PAGE; renderHistory(); };
    });
    root.querySelectorAll("[data-hmore]").forEach(function (b) {
      b.onclick = function () {
        var first = histShown;
        histShown = b.getAttribute("data-hmore") === "all" ? Infinity : histShown + PAGE;
        renderHistory();
        var nr = root.querySelectorAll("tbody tr")[first];
        var na = nr && nr.querySelector("a");
        if (na) na.focus();
      };
    });
    wireGl(root);
  }

  /* ---------------------------------------------------------- team view */

  function renderTeams() {
    var root = el("arb-panel-teams");
    if (!root) return;
    if (!board || !board.rows) {
      root.innerHTML = pxState("loading", "Loading Team View.");
      return;
    }
    var by = {};
    board.rows.forEach(function (r) {
      if (!r.t) return;
      var t = by[r.t] || (by[r.t] = { t: r.t, n: 0, cls: 0, nextArb: 0, nextPre: 0, remArb: 0, remPre: 0 });
      t.n++;
      // Class at the player's first remaining rung, the count the Franchise
      // hub publishes as n_arb. Not "eligible now": a class-3 player whose
      // next season is contracted is counted here too.
      if ((r.c || 0) >= 1) t.cls++;
      // PRE-ARB rungs are the league minimum by rule, not an arbitration
      // award, so every dollar column is split by the rung's token.
      (r.l || []).forEach(function (s) {
        if (s[4] === "PRE-ARB") t.remPre += s[1] || 0; else t.remArb += s[1] || 0;
      });
      // The board season's step for EVERY player (not l[0], whose season varies
      // by player: a pre-arb row may start at 2028, a carried row at 2026), so
      // the season columns are one season for the whole column and the
      // Franchise hub's projected cost, which sums the same tuple, equals the
      // two season columns added together.
      if (r.l && r.l.length) {
        for (var li = 0; li < r.l.length; li++) {
          if (r.l[li][0] === board.season) {
            if (r.l[li][4] === "PRE-ARB") t.nextPre += r.l[li][1] || 0; else t.nextArb += r.l[li][1] || 0;
            break;
          }
        }
      }
    });
    var rows = Object.keys(by).map(function (k) { return by[k]; });
    rows.sort(function (a, b) { return (b.remArb - a.remArb) || (b.remPre - a.remPre); });
    // The league rank is taken BEFORE narrowing, so a narrowed row keeps its
    // place among the thirty.
    var narrowed = teamNarrow && by[teamNarrow] ? teamNarrow : "";
    var season = board.season ? esc(String(board.season)) : "Next season";
    // A club with no rung of a kind owes $0 there, not "$0K".
    function usd(v) { return v ? money(v) : "$0"; }
    var body = rows.map(function (t, i) {
      if (narrowed && t.t !== narrowed) return "";
      return '<tr class="' + (narrowed ? "arb-row-narrow" : "") + '"><td class="mlbstats-col-rank">' + (i + 1) + '</td><td class="arb-l">' + club(t.t) +
        "</td><td>" + t.n + "</td><td>" + t.cls + "</td><td>" + usd(t.nextArb) + "</td><td>" + usd(t.nextPre) +
        "</td><td>" + usd(t.remArb) + "</td><td>" + usd(t.remPre) + "</td></tr>";
    }).join("");
    var narrowNote = narrowed
      ? '<p class="arb-narrow-note">Narrowed to ' + esc(narrowed) + ' (league rank kept). <a href="#teams" id="arb-narrow-clear">All clubs</a></p>'
      : "";
    // COPY PASS 2026-10-03: the sentence that narrated the sort left (the
    // head says "sorted"); the basis, the tender assumption and "not a payroll
    // forecast" stay, one line.
    root.innerHTML = narrowNote +
      '<p class="arb-lede arb-note">Arbitration seasons are model projections, pre-arb seasons the league ' +
      "minimum (own columns). Assumes every player is tendered through his ladder. Not a payroll forecast.</p>" +
      '<div class="mlbstats-scroll"><table class="mlbstats-table arb-table"><thead><tr>' +
      '<th scope="col" class="mlbstats-col-rank">#</th><th scope="col" class="arb-l">Club</th>' +
      '<th scope="col" title="Players on the club\'s arbitration ladder, pre-arb included.">Players</th>' +
      '<th scope="col" title="Players whose first remaining ladder season is arbitration year 1 to 4.">Arb class 1-4</th>' +
      '<th scope="col">' + season + ' arbitration</th><th scope="col">' + season + " pre-arb min.</th>" +
      '<th scope="col">Remaining arbitration<small>sorted</small></th><th scope="col">Remaining pre-arb min.</th></tr></thead><tbody>' + body +
      "</tbody></table></div>";
    var clear = el("arb-narrow-clear");
    if (clear) clear.onclick = function (e) {
      e.preventDefault();
      teamNarrow = "";
      filters.team = "all";
      renderBoard();
      show("teams");
    };
  }

  /* -------------------------------------------------------------- boot */

  function show(which) {
    ["projections", "history", "teams", "model"].forEach(function (k) {
      var panel = el("arb-panel-" + k);
      if (panel) panel.hidden = k !== which;
    });
    document.querySelectorAll("[data-arbsection]").forEach(function (b) {
      var on = b.getAttribute("data-arbsection") === which;
      b.classList.toggle("active", on);
      b.setAttribute("aria-selected", on ? "true" : "false");
    });
    if (which === "history" && !hist && !histErr) loadHistory();
    if (which === "history") renderHistory();
    if (which === "teams") renderTeams();
    try {
      location.hash = "#" + which + (which === "teams" && teamNarrow ? "&team=" + teamNarrow : "") +
        (which === "projections" ? sortHash() : "");
    } catch (e) { /* hash is optional */ }
  }

  function loadHistory() {
    /* Lazily fetched on first open: it is the bigger payload and most visits
       never open it. Its own error state, so a history failure cannot read as
       a board failure. */
    fetch(HIST_URL, { cache: "no-cache" }).then(function (r) {
      if (!r.ok) throw new Error("http " + r.status);
      return r.json();
    }).then(function (d) { hist = d; renderHistory(); })
      .catch(function () { histErr = true; renderHistory(); });
  }

  function load() {
    renderBoard();
    fetch(BOARD_URL, { cache: "no-cache" }).then(function (r) {
      if (!r.ok) throw new Error("http " + r.status);
      return r.json();
    }).then(function (d) {
      board = d;
      // The masthead's glossary term gets its aria-describedby wiring here
      // (QCLA16): the glossary runtime loads after this file, and the board
      // fetch settles after it has run (else the page's load event wires it).
      var head = document.querySelector(".arb-app .section-head");
      if (window.EEPHUS_GL) wireGl(head);
      else window.addEventListener("load", function () { wireGl(head); }, { once: true });
      // The narrowing is honoured only for a club the board carries; the
      // projections filter takes the same club so both views read narrowed.
      if (teamNarrow && !(d.rows || []).some(function (r) { return r.t === teamNarrow; })) teamNarrow = "";
      if (teamNarrow) filters.team = teamNarrow;
      renderBoard();
      if (el("arb-panel-teams") && !el("arb-panel-teams").hidden) renderTeams();
    }).catch(function () { boardErr = true; renderBoard(); });
  }

  function init() {
    document.querySelectorAll("[data-arbsection]").forEach(function (b) {
      b.onclick = function () { show(b.getAttribute("data-arbsection")); };
    });
    var h = (location.hash || "").replace("#", "");
    var sec = h.split("&")[0];
    var tn = TEAM_NARROW_RE.exec(location.hash || "");
    if (tn && sec === "teams") teamNarrow = tn[1];
    var so = SORT_RE.exec(location.hash || "");
    if (so) sort = { key: so[1], dir: so[2] === "d" ? -1 : 1 };
    load();
    if (sec === "history" || sec === "teams" || sec === "model") show(sec);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
