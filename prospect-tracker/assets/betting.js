// Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
// Unauthorized copying of this file, via any medium is strictly prohibited
// Proprietary and confidential
// Written by Noah J. Dengler (@ARKNDJL), 2026
//
// /betting/ module app. Reads data/betting.json (betting_export.py): the
// slate priced by betting_model (team Offense+ / Bullpen+ / starter SEM+ /
// park / home field, Poisson-difference margin), the de-vigged market when an
// odds snapshot exists, model-only prop fair lines, parlay correlation rules,
// and the append-only public record summary.
//
// THREE THINGS THIS FILE TREATS AS NON-NEGOTIABLE:
//
//   1. THE LEGAL BLOCK RENDERS BEFORE ANYTHING ELSE, once, above the section
//      content, so it is on screen for every tab including the failure
//      states. It is built from the payload's `disclaimer` object when one
//      loaded and from LEGAL_FALLBACK when nothing loaded, because "the JSON
//      404'd" must never be the reason a 21+ notice went missing.
//
//   2. THE CALCULATORS AND MY BETS NEVER TOUCH THE PAYLOAD. They are pure
//      client work, so they keep working with no data file, no odds feed, no
//      account and no network. Everything else degrades to a stated empty
//      state that says WHICH input is missing.
//
//   3. NAIVE SAME-GAME PARLAY MATH IS BLOCKED, not warned about. Multiplying
//      correlated legs is arithmetic that looks like a price and is not one.
//
// The bets tracker calls EephusAccount.addBet/listBets/updateBet (owned by
// assets/eephus-account.js) and falls back to localStorage when the account
// layer is absent or the reader is logged out. Nothing here edits that file.
(function () {
  "use strict";

  var DATA_URL = "/data/betting.json";
  var PREVIEW_URL = "/data/betting_preview.json";
  var LS_KEY = "eephus_bets_v1";
  // Section ids are the SHELL'S (build_site's betting page, data-bettingsection
  // attributes), not this file's preference. The shell is the contract; a
  // module that invents its own ids renders a page whose tabs do nothing.
  var SECTIONS = ["potd", "teams", "props", "parlays", "calculators", "record",
                  "validation", "futures", "mybets"];
  var SECTION_PAT = SECTIONS.join("|");
  // The potd label follows the SERVED frame (2026-08-16 Model Watch ruling):
  // "Model Watch" while the gates are closed, "Pick of the Day" when the
  // payload says they opened. The default here is the gates-closed word, and
  // syncTabs rewrites the button the moment the payload lands.
  var SECTION_LABELS = {
    potd: "Model Watch", teams: "Team Bets", props: "Player Props",
    parlays: "Parlays", calculators: "Calculators", record: "The Record",
    validation: "Validation", mybets: "My Bets"
  };

  // ---- the three side artifacts --------------------------------------------
  // /data/betting.json carries the board, the picks and the validation STATE.
  // Three things the validation and record tabs need are published as their own
  // files and are not folded into it:
  //
  //   learning  data/betting_learning.json - the two clocks with their MEASURED
  //             arrival rates, the calibration bins and the per-market split.
  //   evald     data/betting_model_eval.json - run_dispersion, including the
  //             split-quantile sensitivity grid the verdict is taken from. The
  //             payload's `model.backtest` allowlist does not carry it.
  //   clv       data/betting_clv.json - per-pick closing-line value and, when
  //             nothing graded, the reasons why.
  //
  // They are fetched LAZILY, on the first paint of a section that reads one, so
  // the pick tab still costs exactly one request. Each lands as null on a 404
  // and every reader below says which file is missing rather than printing a
  // blank. State is "pending" / "ok" / "fail" and never re-requests.
  var AUX_URL = {
    learning: "/data/betting_learning.json",
    evald: "/data/betting_model_eval.json",
    clv: "/data/betting_clv.json"
  };
  var AUX = { learning: null, evald: null, clv: null };
  var AUX_STATE = { learning: null, evald: null, clv: null };

  var S = { data: null, section: "potd", error: null, legs: [], bets: [], betsSource: "local",
            // Team Bets has two views over the same rows: the game cards and
            // the all-bets leaderboard. Remembered per browser, because a
            // reader who prefers one wants it on the next load too.
            teamView: "cards" };
  var LINKS = null;
  var LAST_HASH = null;

  // Used only when the payload never arrived. Keeping a copy here is
  // duplication on purpose: the alternative is a page that quietly drops its
  // legal notice on exactly the load where something already went wrong.
  var LEGAL_FALLBACK = {
    age: "21+ only.",
    purpose: "Informational and entertainment purposes only. Nothing here is betting advice.",
    legality: "Sports betting is not legal in all states. Know the rules where you are.",
    help: "If gambling stops being fun, call 1-800-GAMBLER.",
    helpline: "1-800-GAMBLER",
    affiliates: "eephus.io takes no affiliate money from any sportsbook and links to none.",
    staking: "Every row on the public record is a flat 1 unit. Kelly is shown as information, never as a stake."
  };

  // ---- the served frame (owner decision 2026-08-16) -------------------------
  // While the three validation gates are closed the payload serves
  // pick_meta.frame = "watch" and the page retires the pick noun: the slots
  // are the model's largest measured disagreements with the market, shown
  // beside their own settled paper record. When the payload says the gates
  // opened (frame "pick"), the pick vocabulary returns everywhere these
  // helpers are read, with no other edit. A payload built before the frame
  // existed reads as watch unless it explicitly says the floor is measured,
  // because every pre-frame payload was a gates-closed payload.
  function slotFrame() {
    var m = (S.data && S.data.pick_meta) || {};
    if (m.frame === "pick" || m.frame === "watch") return m.frame;
    return (m.provisional === false) ? "pick" : "watch";
  }
  function watchMode() { return slotFrame() !== "pick"; }

  // ---- the board's own clock (M12-06, 2026-09-25) ---------------------------
  // Staleness used to be judged at BUILD time only, so on a missed night the
  // page kept serving yesterday's slate as pregame prices under an "odds feed
  // live" chip, the locked Model Watch card included. The client now reads the
  // clock against each game's served first pitch (team_bets[].start, UTC). No
  // price, edge, slot or record row moves; the page only says which prices are
  // no longer on offer. window.EEPHUS_BETTING_NOW (ISO) overrides the clock for
  // tests and render checks.
  function nowMs() {
    var o = (typeof window !== "undefined" && window) ? window.EEPHUS_BETTING_NOW : null;
    var t = o ? Date.parse(o) : NaN;
    return isFinite(t) ? t : Date.now();
  }
  function gameStarted(b) {
    var t = (b && b.start) ? Date.parse(b.start) : NaN;
    return isFinite(t) && t <= nowMs();
  }
  function boardClock() {
    var bets = (S.data && S.data.team_bets) || [];
    var n = 0, started = 0;
    bets.forEach(function (b) {
      var t = (b && b.start) ? Date.parse(b.start) : NaN;
      if (!isFinite(t)) return;
      n++;
      if (gameStarted(b)) started++;
    });
    // "All started" needs a known first pitch on every game: a game with no
    // served start cannot be said to have begun.
    return { n: n, started: started, all: n > 0 && started === n && n === bets.length };
  }
  function staleLine() {
    var clk = boardClock();
    if (clk.all) {
      return '<div class="bt-stale" role="status"><strong>This board is from ' +
        esc((S.data && S.data.slate_date) || "an earlier slate") + ".</strong> Every game on it " +
        "has started, so its prices are historical and no longer on offer.</div>";
    }
    if (clk.started) {
      return '<div class="bt-stale" role="status">' + clk.started + " of " + clk.n +
        " games on this board have started; their prices were pregame and are no " +
        "longer on offer.</div>";
    }
    return "";
  }
  function selNoun() { return watchMode() ? "selection" : "pick"; }
  function selNounPl() { return watchMode() ? "selections" : "picks"; }
  function selNounCap() { return watchMode() ? "Selection" : "Pick"; }

  // ---- the Diamond gate, wired and OFF -------------------------------------
  // Routed through window.EephusDiamond (assets/eephus-diamond.js) since
  // 2026-08-16, the one authoritative contract. The block that lived here
  // probed the account layer's membership SYNCHRONOUSLY at boot, before the
  // deferred account layer could resolve a session, so a paying member's
  // first paint would have been the preview slice with no way back. The
  // helper's onEntitlement callback (wired beside boot below) re-fetches the
  // full payload the moment membership resolves the other way. While gating
  // is off, and while the helper is absent entirely, every reader gets the
  // full payload; this preview build is fully public by owner decision.
  // Genuinely gated data cannot live in /data/ on a static site, so the
  // honest paywall is a Supabase-served path, not this.
  function gated() {
    var D = window.EephusDiamond;
    try { return !!(D && D.gated()); } catch (e) { return false; }
  }
  function dataUrl() { return gated() ? PREVIEW_URL : DATA_URL; }

  // One request per artifact, ever. Returns the parsed file or null; a null
  // means "not loaded", and `auxState` tells the callers whether that is
  // "still in flight", "404" or "never asked", which are three different
  // sentences on screen. The fetch re-paints the current section when it
  // lands, and re-entry is safe because the state is set before the request.
  function aux(key) {
    if (AUX_STATE[key]) return AUX[key];
    AUX_STATE[key] = "pending";
    // The re-paint fires only for a request that settles AFTER this call has
    // returned, which is every real one. A promise that resolves before the
    // return (a stub, a synchronous cache) would otherwise re-render from
    // inside the render that asked for it, and the outer paint would then
    // overwrite the good markup with the empty state it had already built.
    var returned = false;
    function settle(d, ok) {
      AUX[key] = ok ? (d || null) : null;
      AUX_STATE[key] = (ok && d) ? "ok" : "fail";
      if (returned) renderSection();
    }
    fetch(AUX_URL[key], { cache: "no-cache" }).then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    }).then(function (d) { settle(d, true); }).catch(function () { settle(null, false); });
    returned = true;
    return AUX[key];
  }
  function auxState(key) { return AUX_STATE[key] || "idle"; }
  // The one sentence a panel prints instead of a number it does not have.
  function auxMissing(key) {
    var st = auxState(key);
    if (st === "pending") return "Loading " + AUX_URL[key] + ".";
    return AUX_URL[key] + " did not load. The nightly build writes it.";
  }

  // ---- helpers --------------------------------------------------------------
  function el(id) { return document.getElementById(id); }
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
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
  function num(v, d) { return (v == null || isNaN(v)) ? "-" : Number(v).toFixed(d == null ? 1 : d); }
  function pct(v, d) { return (v == null || isNaN(v)) ? "-" : (Number(v) * 100).toFixed(d == null ? 1 : d) + "%"; }
  function signed(v, d) {
    if (v == null || isNaN(v)) return "-";
    var n = Number(v);
    return (n > 0 ? "+" : "") + n.toFixed(d == null ? 1 : d);
  }
  function teamLogo(org) {
    return (window.EEPHUS_HUB && EEPHUS_HUB.teamLogo && org) ? EEPHUS_HUB.teamLogo(org) : "";
  }
  function hrefFor(mlbam) {
    var e = LINKS && LINKS.byMlbam && LINKS.byMlbam[String(mlbam)];
    return (e && e.key) ? ("/projections/#player=" + e.key) : null;
  }
  function nameLink(mlbam, name) {
    var h = hrefFor(mlbam);
    return h ? '<a class="bt-link" href="' + esc(h) + '">' + esc(name) + "</a>" : esc(name);
  }
  // GLOSSARY TERMS. The contract is assets/eephus-gl.js: a [data-gl] span whose
  // value is a slug that EXISTS in data/glossary.json, plus one wire() call per
  // rendered container.
  //
  // THE SPAN NO LONGER CARRIES .g-term ITSELF, and that one change is what lets
  // the betting vocabulary ship. eephus-gl's wire() adds the class only when it
  // resolves the slug against the loaded artifact and returns early when it
  // cannot; the class is what styles a term as clickable, so emitting it here
  // was what made an unknown slug render as a term that defines nothing. Now an
  // unresolvable slug degrades to plain text on its own, and lights up the
  // moment the artifact carries it.
  //
  // The betting vocabulary (edge, vig, de-vig, fair line, implied probability,
  // EV per unit, unit, Kelly, moneyline, runline, total, parlay, CLV,
  // provisional pick, policy floor, Brier) is registered in
  // build_glossary_data.BETTING_ENTRIES and merged into data/glossary.json by
  // `python build_glossary_data.py --betting`. Until that merge runs on a given
  // checkout, these words read as plain text rather than as a tooltip pointing
  // at nothing.
  function gl(label, slug) {
    return '<span data-gl="' + esc(slug) + '">' + esc(label) + "</span>";
  }
  function wireGl(node) {
    try { if (node && window.EEPHUS_GL && EEPHUS_GL.wire) EEPHUS_GL.wire(node); }
    catch (e) { /* the glossary is enrichment; the page works without it */ }
  }
  function note(text) { return '<div class="bt-note">' + text + "</div>"; }
  function empty(title, why) {
    return pxState("empty", "<strong>" + esc(title) + "</strong>" +
      (why ? " " + esc(why) : ""));
  }
  // ---- sortable tables (owner ask 2026-09-05) --------------------------------
  // Every data table the module renders sorts on a header click, in both
  // directions, with nulls sinking. This mirrors the mlbstats.js header
  // contract (scope=col, tabindex, aria-sort, Enter and Space, the is-sorted
  // class; no role=button, which would hide aria-sort from a screen reader) but works on the RENDERED cells rather than a column spec: the
  // betting tables are HTML strings built from a dozen payload shapes, and one
  // generic wiring beats twelve column specs that drift. A cell may carry
  // data-sort to override its display text; otherwise the first token of the
  // text is parsed. Numbers, signed odds (+150 / -110), percentages (12.3%),
  // units (+1.5u), dollars and thousands separators all parse as numbers; a
  // bare "-", empty text or n/a is null; everything else compares as text.
  // The parser and comparator are pure and exposed for tests.
  function btSortValue(raw) {
    var t = String(raw == null ? "" : raw).replace(/\s+/g, " ").trim();
    if (!t) return null;
    var low = t.toLowerCase();
    if (low === "-" || low === "n/a" || low === "none" || low === "null") return null;
    var tok = t.split(" ")[0].replace(/,/g, "").replace(/^\$/, "").replace(/[%ux]$/i, "");
    if (/^[+-]?\d+(\.\d+)?$/.test(tok)) return { n: parseFloat(tok), s: low };
    return { n: null, s: low };
  }
  // Returns <0 when a sorts before b in the requested direction. Nulls always
  // sort LAST regardless of direction; ties keep source order (the caller
  // breaks them by index).
  function btCompare(a, b, dir) {
    var an = (a == null), bn = (b == null);
    if (an && bn) return 0;
    if (an) return 1;
    if (bn) return -1;
    var sign = (dir === "asc") ? 1 : -1;
    if (a.n != null && b.n != null) return (a.n - b.n) * sign;
    if (a.n != null) return -1 * sign;      // numbers before text
    if (b.n != null) return 1 * sign;
    if (a.s < b.s) return -1 * sign;
    if (a.s > b.s) return 1 * sign;
    return 0;
  }
  function btSortStoreKey(key) { return "eephus.betting.sort." + key; }
  function btSortTable(table, ci, dir, key, silent) {
    var ths = table.querySelectorAll("thead th");
    var th = ths[ci];
    var tbody = table.querySelector("tbody");
    if (!th || !tbody) return;
    var rows = Array.prototype.slice.call(tbody.querySelectorAll("tr")).filter(function (r) {
      return r.parentNode === tbody;
    });
    if (!rows.length) return;
    var vals = rows.map(function (r) {
      var td = r.children[ci];
      if (!td) return null;
      var ds = td.getAttribute("data-sort");
      return btSortValue(ds != null ? ds : td.textContent);
    });
    var numeric = vals.some(function (v) { return v && v.n != null; });
    var cur = th.getAttribute("aria-sort");
    if (!dir) dir = (cur === "descending") ? "asc" : (cur === "ascending") ? "desc" : (numeric ? "desc" : "asc");
    var idx = rows.map(function (_, i) { return i; });
    idx.sort(function (a, b) { var c = btCompare(vals[a], vals[b], dir); return c !== 0 ? c : a - b; });
    idx.forEach(function (i) { tbody.appendChild(rows[i]); });
    Array.prototype.forEach.call(ths, function (h) {
      if (h.getAttribute("aria-sort")) h.setAttribute("aria-sort", "none");
      h.classList.remove("is-sorted");
    });
    th.setAttribute("aria-sort", dir === "asc" ? "ascending" : "descending");
    th.classList.add("is-sorted");
    if (!silent && key) {
      try { localStorage.setItem(btSortStoreKey(key), JSON.stringify({ col: ci, dir: dir })); }
      catch (e) { /* storage is a convenience, never a dependency */ }
    }
  }
  function wireSortableTables(root) {
    if (!root || !root.querySelectorAll) return;
    var tables = root.querySelectorAll("table.bt-table");
    if (!tables || !tables.length) return;
    Array.prototype.forEach.call(tables, function (table, ti) {
      if (table.getAttribute("data-bt-sortable")) return;        // idempotent
      var thead = table.querySelector("thead"), tbody = table.querySelector("tbody");
      if (!thead || !tbody) return;
      var ths = thead.querySelectorAll("th");
      if (!ths || !ths.length) return;
      table.setAttribute("data-bt-sortable", "1");
      var labels = Array.prototype.map.call(ths, function (h) { return String(h.textContent || "").trim(); });
      var key = table.getAttribute("data-sort-key") ||
        ((S.section || "page") + ":" + ti + ":" + labels.join("|").slice(0, 80));
      Array.prototype.forEach.call(ths, function (th, ci) {
        if (!labels[ci]) return;                                   // blank action columns
        th.setAttribute("scope", "col");
        th.setAttribute("tabindex", "0");
        th.setAttribute("aria-sort", "none");
        th.classList.add("bt-sortable");
        var activate = function () { btSortTable(table, ci, null, key, false); };
        th.addEventListener("click", activate);
        th.addEventListener("keydown", function (e) {
          if (e.key !== "Enter" && e.key !== " ") return;
          e.preventDefault();
          activate();
        });
      });
      var saved = null;
      try { saved = JSON.parse(localStorage.getItem(btSortStoreKey(key)) || "null"); }
      catch (e) { saved = null; }
      var def = table.getAttribute("data-default-sort");
      if (saved && saved.col != null && ths[saved.col]) btSortTable(table, +saved.col, saved.dir, key, true);
      else if (def) {
        var parts = String(def).split(":");
        if (ths[+parts[0]]) btSortTable(table, +parts[0], parts[1] || "desc", key, true);
      }
    });
  }
  if (typeof window !== "undefined") {
    window.EEPHUS_BETTING_SORT = { value: btSortValue, compare: btCompare, wire: wireSortableTables };
  }

  function fmtOdds(v) {
    if (v == null || isNaN(v)) return "-";
    var n = Math.round(Number(v));
    return (n > 0 ? "+" : "") + n;
  }

  // ---- odds math (shared by the boards and the calculators) -----------------
  // One implementation, used by every surface on the page, so a number in the
  // calculator can never disagree with the same number on a board.
  // American prices below 100 in absolute value do not exist: the scale runs
  // +100 / -100 outward from an even-money bet and there is nothing in the gap.
  // Without the floor, a half-typed "-1" converted to decimal 101 and printed
  // "+10000" as though it were a price a book had posted.
  function amToDec(a) {
    var n = Number(a);
    if (!isFinite(n) || Math.abs(n) < 100) return null;
    return 1 + (n > 0 ? n / 100 : 100 / Math.abs(n));
  }
  function decToAm(d) {
    var n = Number(d);
    if (!isFinite(n) || n <= 1) return null;
    return n >= 2 ? Math.round((n - 1) * 100) : Math.round(-100 / (n - 1));
  }
  function decToImplied(d) {
    var n = Number(d);
    return (!isFinite(n) || n <= 1) ? null : 1 / n;
  }
  function impliedToDec(p) {
    var n = Number(p);
    return (!isFinite(n) || n <= 0 || n >= 1) ? null : 1 / n;
  }
  // Proportional de-vig, the same method betting_model.devig uses server-side.
  function devig(decimals) {
    var raw = [], sum = 0, i;
    for (i = 0; i < decimals.length; i++) {
      var q = decToImplied(decimals[i]);
      if (q == null) return null;
      raw.push(q); sum += q;
    }
    if (!sum) return null;
    return raw.map(function (q) { return q / sum; });
  }
  // THE PUSH IS PART OF THE BET, NOT PART OF THE ODDS. On a whole-number total
  // the book returns the stake when the total lands exactly on the line, so a
  // refund is not a loss. `p` is already CONDITIONAL on no push (that is what
  // betting_model.total_side_probabilities returns), which makes the honest
  // number the conditional EV scaled by the chance the bet resolves at all.
  // betting_export._priced_side applies exactly this factor at the call site,
  // and it moved published picks: the unadjusted number overstates a whole
  // number by 1 / (1 - p_push), measured 1.140x to 1.163x on 2026-08-09.
  // Omitting the third argument is the half-point case and changes nothing.
  function evPerUnit(p, dec, pPush) {
    var pp = (pPush > 0 && pPush < 1) ? Number(pPush) : 0;
    return (1 - pp) * (p * (dec - 1) - (1 - p));
  }
  function kelly(p, dec) {
    var b = dec - 1;
    if (b <= 0) return 0;
    return Math.max(0, (p * b - (1 - p)) / b);
  }

  // ---- legal block ----------------------------------------------------------
  // THE SHELL OWNS THIS IN PRODUCTION. build_site's betting page ships a
  // `.betting-disclaimer` card above the section nav, so the 21+ notice is on
  // screen for every tab by construction and this function returns without
  // doing anything.
  //
  // What lives here is the SAFETY NET. If a shell revision ever drops that
  // card, or if the module is mounted somewhere that never had one, the notice
  // is built from the payload (or from LEGAL_FALLBACK when the payload never
  // arrived) and inserted above the section content. A legal notice that
  // depends on either a successful fetch or an unchanged template is not a
  // legal notice.
  function renderLegal() {
    var host = el("betting-legal");
    if (!host) {
      if (document.querySelector(".betting-disclaimer")) return;   // shell carries it
      var sec = el("betting-section") || el("betting-app-root");
      if (!sec) return;
      host = document.createElement("div");
      host.id = "betting-legal";
      var anchor = el("betting-banner") || el("betting-app-root");
      if (anchor && anchor.parentNode === sec) sec.insertBefore(host, anchor);
      else sec.insertBefore(host, sec.firstChild);
    }
    var d = (S.data && S.data.disclaimer) || LEGAL_FALLBACK;
    host.className = "bt-legal";
    host.setAttribute("role", "note");
    host.innerHTML =
      '<div class="bt-legal-badge">21+</div>' +
      '<div class="bt-legal-body">' +
      "<p>" + esc(d.purpose || LEGAL_FALLBACK.purpose) + " " +
      esc(d.legality || LEGAL_FALLBACK.legality) + "</p>" +
      "<p>" + esc(d.affiliates || LEGAL_FALLBACK.affiliates) + " " +
      esc(d.staking || LEGAL_FALLBACK.staking) + "</p>" +
      '<p class="bt-legal-help">' + esc(d.help || LEGAL_FALLBACK.help) + "</p>" +
      "</div>";
  }

  // ---- the vintage state ----------------------------------------------------
  // betting_export carries `model.validation` out of the backtest artifact:
  // which of the two grading modes produced each block, how much dated
  // leaderboard history exists, how many games the honest mode could grade
  // with it, and the three gates on the minimum-edge threshold. Everything in
  // this section READS that block. It computes nothing, and in particular it
  // projects no date for validation: the gates give a game count, and turning
  // a count into a calendar date needs a rate the payload does not carry.
  //
  // A payload built before that lane existed has no `validation` key. Every
  // reader here returns null in that case and the callers say so out loud,
  // because "unknown" and "measured zero" are different facts.
  // null means the key is absent (an old payload). A block with
  // `available: false` means the key is present and says the artifact is
  // missing. The callers distinguish the two.
  function vstate() {
    return ((S.data && S.data.model) || {}).validation || null;
  }
  function gateById(v, id) {
    var gs = ((v || {}).gate || {}).gates || [];
    for (var i = 0; i < gs.length; i++) if (gs[i].id === id) return gs[i];
    return null;
  }
  function haveText(g) {
    if (!g) return "-";
    var h = g.have;
    // "none measured" and not "not measured": this string reads both as a
    // table cell and inside "has ...", and only one of the two works in both.
    return (h == null) ? "none measured" : String(h);
  }
  function sentence(s) {
    s = String(s || "");
    return s ? s.charAt(0).toUpperCase() + s.slice(1) : "";
  }

  // HOW FAR SHORT, in the gate's own unit. "closed" tells a reader nothing
  // about whether he is waiting a week or a decade; 389 games does.
  //
  // THE THRESHOLD IS READ, NEVER ASSUMED. `vintage_sample` takes it from the
  // served `min_graded_games_for_min_edge`; the other two take it out of the
  // gate's OWN `need` string, which is the only place they publish it. No
  // number in this function is written down in this file, so a gate that moves
  // its bar server-side moves this column with it.
  function gateNeedValue(g, v) {
    var id = String((g || {}).id || ""), need = String((g || {}).need || ""), m;
    if (id === "vintage_sample") {
      return { n: ((v || {}).vintage || {}).min_graded_games_for_min_edge, unit: "games" };
    }
    if (id === "out_of_sample_skill") {
      m = /t\s*>=\s*(-?[\d.]+)/.exec(need);
      return { n: m ? Number(m[1]) : null, unit: "t" };
    }
    if (id === "graded_price_history") {
      m = /at least (\d+)/.exec(need);
      return { n: m ? Number(m[1]) : null, unit: "settled rows" };
    }
    m = /(-?\d+(?:\.\d+)?)/.exec(need);
    return { n: m ? Number(m[1]) : null, unit: "" };
  }
  // THE `why` PARAGRAPH IS THE WIDEST THING IN THE GATE TABLE, and on a 390px
  // phone a five-column table carrying it scrolls the whole document sideways.
  // It ships as a disclosure that is OPEN on a wide viewport and CLOSED on a
  // narrow one, so the desktop reader loses nothing and the phone reader gets a
  // table that fits with the same words one tap away. The open state is decided
  // at render time because CSS cannot open a <details> and hiding the paragraph
  // outright would delete the reason rather than fold it.
  function narrowView() {
    try {
      return !!(window.matchMedia && window.matchMedia("(max-width:640px)").matches);
    } catch (e) { return false; }
  }
  function whyBlock(text, label) {
    if (!text) return "";
    return '<details class="bt-gate-more"' + (narrowView() ? "" : " open") +
      '><summary class="bt-gate-sum">' + esc(label || "why this gate exists") +
      '</summary><div class="bt-gate-why">' + esc(text) + "</div></details>";
  }

  function gateDistance(g, v) {
    if (g && g.open) return { text: "open", short: false };
    var have = (g || {}).have;
    var nv = gateNeedValue(g, v);
    if (typeof have !== "number" || nv.n == null) {
      return { text: "not measurable", short: false };
    }
    var gap = nv.n - have;
    if (gap <= 0) return { text: "at the bar", short: false };
    var digits = (nv.unit === "t") ? 3 : 0;
    return { text: num(gap, digits) + " " + nv.unit + " short", short: true };
  }
  // The one sentence the pick section leads with. Built from the gate the
  // reader can actually count, so it reads "600 needed, 0 today" rather than
  // "the model is unvalidated" with no way to check the claim.
  function noPickHeadline(v) {
    var lead = "No " + selNoun() + ": ";
    if (!v) return lead + "this payload carries no validation state; the model is unvalidated.";
    if (v.available === false) {
      return lead + (v.reason || "the validation state is unknown") + ".";
    }
    var g = gateById(v, "vintage_sample");
    if (g) {
      return lead + "the model is unvalidated until " + g.need + " exist; " +
        haveText(g) + " today.";
    }
    return lead + "the model is unvalidated and no minimum edge has been measured.";
  }

  // THE VINTAGE BLURB HAS TWO DOORS, AND THE SERVED ONE IS THE STALE ONE
  // (2026-09-18). `betting_export.MODE_MEANING` is a SOURCE CONSTANT that the
  // nightly export COPIES into data/betting.json, and this page renders the
  // copy. A repair to that constant therefore reaches a reader only when the
  // export next writes the file. The sentence repaired on 2026-09-18 was false
  // about the starter, and the panel below it now states the truth, so a stale
  // payload would have put the two on one screen contradicting each other. The
  // current text also lives here, in the door that deploys with the page, and
  // is preferred over the payload's copy of it.
  //
  // THIS IS NOT A SECOND OPINION. `test_betting_policy_copy` pins this table
  // byte for byte against `betting_export.MODE_MEANING`, and renders the tab
  // against a payload carrying the OLD sentence to prove which door wins. A
  // payload that carries no `mode_meaning` at all still renders nothing, as
  // before: this table is a fresher copy of a served string, never the only
  // copy of one.
  var MODE_MEANING = {
    contaminated: "Team inputs are season-to-date leaderboards, so every graded game " +
      "sits inside its own features. This measures calibration, not " +
      "skill, and it cannot validate anything.",
    vintage: "Every game is priced on a leaderboard snapshot whose knowledge " +
      "cutoff is strictly before that game: team offense, team run " +
      "prevention, the starter's SEM+ ratings and the park index all come " +
      "out of that snapshot. WHICH starter does not: his identity is the " +
      "probable on the completed-game row, which is the final feed's, " +
      "while the served board prices the probable listed at the nightly " +
      "build. Who starts is fixed before first pitch, so that is a " +
      "difference in information and not an outcome leak. A game with no " +
      "such snapshot is skipped, not graded on today's numbers, and a " +
      "game whose snapshot predates the stored park column is priced with " +
      "the park term at neutral rather than on the live index. This is " +
      "the only mode that can validate the model."
  };
  function modeMeaning(v, mode) {
    var served = ((v || {}).mode_meaning || {})[mode];
    if (!served) return "";
    return MODE_MEANING[mode] || served;
  }

  function modeTag(mode, honest) {
    if (!mode) return '<span class="bt-dim">-</span>';
    return '<span class="bt-tag ' + (honest ? "bt-tag-ok" : "bt-tag-warn") + '">' +
      esc(mode) + "</span>";
  }

  function validationPanel() {
    var v = vstate();
    var rows = ['<div class="bt-panel-hd">Is the model validated?</div>'];
    if (!v) {
      return '<div class="bt-panel">' + rows.join("") +
        "<p>No. This payload predates the validation state; treat every number here as " +
        "unvalidated.</p></div>";
    }
    if (v.available === false) {
      return '<div class="bt-panel">' + rows.join("") + "<p><strong>No.</strong> " +
        esc(sentence(v.reason) || "The validation state is unknown.") + "</p></div>";
    }
    var vin = v.vintage || {}, cov = v.coverage || {}, gate = v.gate || {};
    var need = vin.min_graded_games_for_min_edge;

    rows.push("<p><strong>" + (v.validated ? "Yes." : "No.") + "</strong> " +
      (v.validated
        ? "The vintage mode cleared every gate below; the headline numbers come from it."
        : "Headline numbers come from the <strong>" +
          esc(v.headline_mode || "contaminated") + "</strong> mode, which cannot validate. " +
          esc(modeMeaning(v, "contaminated"))) + "</p>");

    if ((v.mode_meaning || {}).vintage) {
      rows.push("<p><strong>" + gl("Vintage mode", "vintage_grading") + ".</strong> " +
        esc(modeMeaning(v, "vintage")) + " Graded " +
        (vin.n_graded == null ? "-" : vin.n_graded) + " of " +
        (v.n_games_completed == null ? "-" : v.n_games_completed) + " completed games; skipped " +
        (vin.n_skipped_no_vintage == null ? "-" : vin.n_skipped_no_vintage) +
        " with no earlier snapshot.</p>");
    }

    rows.push('<div class="bt-kv">' +
      kv("Dated leaderboard snapshots", cov.n_vintages == null ? "-" : cov.n_vintages) +
      kv("Snapshot range", cov.first ? esc(cov.first) + " to " + esc(cov.last) : "none yet") +
      kv("Missing days inside that range", (cov.missing_dates || []).length) +
      kv("First game date a snapshot can price",
         cov.earliest_gradable_game_date ? esc(cov.earliest_gradable_game_date) : "-") +
      kv("Games graded by the vintage mode", vin.n_graded == null ? "-" : vin.n_graded) +
      kv("Graded games needed for a threshold", need == null ? "-" : need) +
      "</div>");

    if ((gate.gates || []).length) {
      rows.push('<div class="bt-panel-sub">Gates on a published ' +
        selNoun() + "</div>");
      rows.push('<div class="bt-scroll mlbstats-scroll"><table class="bt-table mlbstats-table"><thead><tr>' +
        '<th class="bt-l">Gate</th><th class="bt-l">What it needs</th><th>Have</th>' +
        "<th>Distance</th><th>State</th></tr></thead><tbody>" +
        gate.gates.map(function (g) {
          var d = gateDistance(g, v);
          return '<tr><td class="bt-l">' + esc(g.id) + "</td>" +
            '<td class="bt-l bt-gate-need">' + esc(g.need || "") + whyBlock(g.why) + "</td>" +
            "<td>" + esc(haveText(g)) + "</td>" +
            '<td class="' + (d.short ? "bt-neg" : "") + '">' + esc(d.text) + "</td>" +
            '<td><span class="bt-tag ' + (g.open ? "bt-tag-ok" : "bt-tag-warn") + '">' +
            (g.open ? "open" : "closed") + "</span></td></tr>";
        }).join("") + "</tbody></table></div>");
      rows.push(note(esc(gate.n_open + " of " + gate.n_gates + " gates are open. ") +
        esc(gate.policy || "")));
    }

    rows.push('<div class="bt-panel-sub">When that changes</div>');
    rows.push("<p>One snapshot lands per night; a game is gradable once a snapshot predates " +
      "it. The sample starts at games on or after " +
      (cov.earliest_gradable_game_date ? esc(cov.earliest_gradable_game_date) :
        "the first snapshot night") + " and grows toward " +
      (need == null ? "the threshold" : need) + ". Clock A (Validation tab) carries the " +
      "measured arrival rate, its window, and a labelled projection.</p>");
    if (v.generated_at) {
      rows.push('<div class="bt-asof">Backtest artifact generated ' + esc(v.generated_at) +
        (v.model_version ? " &middot; " + esc(v.model_version) : "") + "</div>");
    }
    return '<div class="bt-panel">' + rows.join("") + "</div>";
  }

  // ---- what the graded sample was priced on ---------------------------------
  // OWNER DECISION 2026-09-18. The headline above states the vintage Brier and
  // the skill t. Until now the page stated those two numbers without stating
  // what priced the sample they come from, and one of the three bases is a
  // qualifier a reader has to have: the backtest grades on the FINAL feed's
  // probable, while the served board prices the probable listed at the nightly
  // build. That is a difference in INFORMATION, not an outcome leak, because
  // who starts is fixed before first pitch, and this panel has to say both
  // halves or it implies a leak that is not there.
  //
  // All three blocks already shipped and none is computed here. `park_basis`
  // rides the payload's own vintage block; `feature_basis` and `starter_basis`
  // ride data/betting_model_eval.json, which this page already fetches as
  // AUX.evald for the dispersion grid and the benchmark ladder. Every number
  // below is READ: nothing on this page sums, averages or rounds them.
  function starterBasisBlock(sb) {
    if (!sb) {
      return chartAbsent("Starter basis",
        (auxState("evald") === "ok"
          ? "data/betting_model_eval.json carries no starter_basis block."
          : auxMissing("evald")));
    }
    var eq = sb.equals_first_pitcher_used || {};
    var ag = (sb.doors || {}).agreement || {};
    var c = sb.counts || {};
    var rows = ['<div class="bt-panel-sub">The starter</div>'];
    rows.push("<p>The backtest prices each graded game on the starter named by the " +
      "<strong>final feed</strong>, read off the completed-game row. The served board " +
      "prices the probable listed at the nightly build, which is not that field, so " +
      "the graded pricer holds a starter the board did not always have. Who starts is " +
      "fixed before first pitch: this is a difference in <strong>information</strong>, " +
      "not an outcome leak.</p>");
    rows.push('<div class="bt-kv">' +
      kv("Graded starter", esc(sb.source || "-")) +
      kv("Stored as", esc(sb.field || "-")) +
      kv("The served board reads", esc(sb.served_board_reads || "-")) +
      kv("Sides equal to the first pitcher actually used",
         (eq.equal == null || eq.sides_compared == null) ? "-"
           : (eq.equal + " of " + eq.sides_compared +
              (eq.differ == null ? "" : ", " + eq.differ + " differ") +
              (eq.sides_without_a_probable == null ? ""
                : ", " + eq.sides_without_a_probable + " with no probable") +
              (eq.measured_on ? " (" + esc(eq.measured_on) + ")" : ""))) +
      kv("The two doors into that field agree on",
         (ag.sides_compared == null) ? "-"
           : (ag.sides_compared + " sides across " +
              (ag.n_games == null ? "-" : ag.n_games) + " games, " +
              (ag.differ == null ? "-" : ag.differ) + " differences" +
              (ag.measured_on ? " (" + esc(ag.measured_on) + ")" : ""))) +
      kv("Games with a starter named on both sides",
         (c.both_sides_named == null) ? "-"
           : (c.both_sides_named + " of " + (c.n_games == null ? "-" : c.n_games))) +
      "</div>");
    // NEITHER COUNT IS THE GRADED SAMPLE, and both sit inside a panel whose
    // headline number is. The coverage counts walk the completed-game cache;
    // the agreement rate is a frozen archive of a smaller cache on the day it
    // was measured. The block's own served note says the second half, and the
    // page owes the first.
    rows.push('<div class="bt-clock-fine">Every count here runs over the ' +
      "completed-game cache, which is not the graded sample: a game is in that " +
      "cache whether or not a dated snapshot could price it.</div>");
    if (eq.denominator_note) rows.push(note(esc(eq.denominator_note) + "."));
    return rows.join("");
  }

  // THE PARK COUNTS ARE THE GRADABLE POOL, NOT THE GRADED SAMPLE. They cover
  // every game a dated snapshot could price, which is the fit half and the
  // graded half together, so their denominator is larger than the Brier's and
  // the rows have to say which pool they walk. The fit half is never graded
  // (house rule), and counting it here does not grade it: a park index is an
  // input, not a result.
  function parkBasisBlock(pb, vin, ev) {
    if (!pb) {
      return chartAbsent("Park basis",
        "this artifact predates the stored park column, so it does not know " +
        "which index priced its games.");
    }
    var v = vin || {}, e = ev || {};
    var pool = (v.n_gradable == null) ? e.n_gradable : v.n_gradable;
    var fit = (v.n_fit_games == null) ? e.n_fit_games : v.n_fit_games;
    var graded = (v.n_graded == null) ? e.n_graded : v.n_graded;
    var rows = ['<div class="bt-panel-sub">The park index</div>'];
    rows.push('<div class="bt-kv">' +
      kv("Source", esc(pb.source || "-")) +
      kv("The pool these rows count",
         pool == null ? "every gradable game"
           : (pool + " gradable games" +
              (fit == null || graded == null ? ""
                : " (" + fit + " fitted, " + graded + " graded)"))) +
      kv("Priced on their own dated park index",
         pb.n_games_vintage_park == null ? "-" : pb.n_games_vintage_park) +
      kv("Priced with the park term at neutral",
         pb.n_games_neutral_park == null ? "-" : pb.n_games_neutral_park) +
      kv("Of those, inside the eval window",
         pb.n_eval_games_neutral_park == null ? "-" : pb.n_eval_games_neutral_park) +
      "</div>");
    if (pb.note) rows.push(note(esc(pb.note) + "."));
    return rows.join("");
  }

  // The DARK columns. They price nothing, and the block says so in its own
  // served note; it is here because a reader owed "what priced this sample"
  // is also owed "what did not", and because the counts are the only public
  // record of which captured column a vintage record actually carried.
  function featureBasisBlock(fb) {
    if (!fb) {
      return chartAbsent("Feature basis",
        (auxState("evald") === "ok"
          ? "data/betting_model_eval.json carries no feature_basis block."
          : auxMissing("evald")));
    }
    var keys = Object.keys(fb).filter(function (k) {
      var v = fb[k];
      return v && typeof v === "object" && v.n_eval_games;
    }).sort();
    var rows = ['<div class="bt-panel-sub">The dark columns, which priced nothing</div>'];
    if (!keys.length) {
      rows.push(chartAbsent("Feature basis", "no column carries an eval-window count."));
      return rows.join("");
    }
    rows.push('<div class="bt-scroll mlbstats-scroll">' +
      '<table class="bt-table mlbstats-table"><thead><tr>' +
      '<th class="bt-l">Column</th><th>Populated</th><th>Null, stated</th>' +
      "<th>Predates it</th></tr></thead><tbody>" +
      keys.map(function (k) {
        var n = fb[k].n_eval_games || {};
        return '<tr><td class="bt-l">' + esc(k) + "</td><td>" +
          (n.populated == null ? "-" : n.populated) + "</td><td>" +
          (n.null_stated == null ? "-" : n.null_stated) + "</td><td>" +
          (n.predates_column == null ? "-" : n.predates_column) + "</td></tr>";
      }).join("") + "</tbody></table></div>");
    rows.push('<div class="bt-clock-fine">Eval-window games, the graded sample ' +
      'the Brier above is measured on. "Predates it" is a vintage record ' +
      "written before that column existed. A gradable-pool count rides beside " +
      "each one in the artifact.</div>");
    if (typeof fb.note === "string") rows.push(note(esc(fb.note) + "."));
    return rows.join("");
  }

  // THREE BLOCKS, THREE POOLS, AND THE PANEL SAYS SO (2026-09-18). The three
  // bases do not count over one denominator, and a heading that implied they
  // did would be its own small lie: the park counts run over the GRADABLE pool
  // (the fit half and the graded half together), the dark-column counts run
  // over the GRADED sample alone, and the starter counts run over the
  // completed-game cache, which is larger than either and is not a grading
  // pool at all. Every number is read. The lead names the graded sample once,
  // so a reader has the headline denominator before the blocks start, and each
  // block names its own beside its rows.
  function basisPanel() {
    var v = vstate();
    var e = aux("evald") || {};
    var vin = (v || {}).vintage || {};
    var ev = e.vintage || {};
    var graded = (vin.n_graded == null) ? (ev.n_graded == null ? null : ev.n_graded)
      : vin.n_graded;
    var rows = ['<div class="bt-panel-hd">What the graded sample was priced on</div>'];
    rows.push("<p>The Brier and the skill t above are measured on the " +
      gl("vintage", "vintage_grading") + " sample" +
      (graded == null ? "" : " of " + graded + " graded games") +
      ". These are the three bases that sample was built from, as the backtest " +
      "artifact records them. They count over three different pools, each named " +
      "with its block.</p>");
    rows.push(starterBasisBlock(e.starter_basis || null));
    rows.push(parkBasisBlock(vin.park_basis || ev.park_basis || null, vin, ev));
    rows.push(featureBasisBlock(ev.feature_basis || null));
    return '<div class="bt-panel">' + rows.join("") + "</div>";
  }

  // ---- the feed-health strip ------------------------------------------------
  // THE MODULE STATE IS "THE CLOSE HALF HAS NEVER RUN" AND NOTHING ON SCREEN
  // SAID SO. Every price on this page comes from an OPEN snapshot. The CLOSE
  // snapshot is a separate cron, it writes the only evidence CLV can ever be
  // graded from, and it is unrecoverable after the fact: a slate whose close
  // was never captured can never be graded, no matter what runs tomorrow.
  //
  // So this strip renders ABOVE THE TABS, on every section, on every load,
  // including the load where the payload 404'd. `status.feed_health` is
  // measured off .cache/odds/ by betting_export.snapshot_health, and its
  // `diagnosis` names the REPAIR rather than the symptom; it rides here as the
  // title so an operator gets it on hover without a second click.
  function feedHealthHost() {
    var host = el("betting-feedhealth");
    if (host) return host;
    // The shell ships the host. This is the skew fallback: a shell built
    // before this lane still gets the strip, above the section content.
    var sec = el("betting-section");
    var nav = document.querySelector(".mlbstats-sectionnav");
    host = document.createElement("div");
    host.id = "betting-feedhealth";
    if (nav && nav.parentNode) nav.parentNode.insertBefore(host, nav);
    else if (sec) sec.insertBefore(host, sec.firstChild);
    else return null;
    return host;
  }

  function fhSeg(label, value, warn) {
    return '<span class="bt-fh-seg' + (warn ? " bt-fh-warn" : "") + '">' +
      '<span class="bt-fh-k">' + esc(label) + "</span>" +
      '<span class="bt-fh-v">' + esc(value) + "</span></span>";
  }

  function renderFeedHealth() {
    var host = feedHealthHost();
    if (!host) return;
    var d = S.data || null;
    var st = (d && d.status) || {};
    var fh = st.feed_health || null;
    var segs = [];
    if (!d) {
      segs.push(fhSeg("odds", "payload not loaded", true));
      segs.push(fhSeg("board", "unknown", true));
    } else {
      // OPEN. The capture the board was actually priced from, which is the one
      // that matters; `odds_kind` says which half of the day it is.
      var cap = st.odds_captured_at ? String(st.odds_captured_at).slice(0, 10) : null;
      segs.push(fhSeg("odds " + (st.odds_kind || "open"), cap || "none cached", !cap));
      // CLOSE. Zero is the state this strip exists for, and it is stated in
      // capitals because it is not a degraded reading of a working job, it is
      // a job that has never run.
      // CLOSE, only while CLV is served. Left unconditional this painted the
      // whole strip red and read "NEVER CAPTURED" forever over a capture the
      // module no longer uses, which is an alarm about a retired feature.
      if (clvEnabled()) {
        var nClose = fh ? fh.n_slates_with_close : null;
        var nSlates = fh ? fh.n_slates : null;
        var closeTxt, closeWarn;
        if (!fh) { closeTxt = "not measured"; closeWarn = true; }
        else if (!nClose) { closeTxt = "NEVER CAPTURED"; closeWarn = true; }
        else if (nClose < nSlates) { closeTxt = nClose + " of " + nSlates + " slates"; closeWarn = true; }
        else { closeTxt = "all " + nSlates + " slates"; closeWarn = false; }
        segs.push(fhSeg("close", closeTxt, closeWarn));
      }
      segs.push(fhSeg("board", d.slate_date || "unknown", !d.slate_date));
      segs.push(fhSeg("games", String(d.n_games == null ? 0 : d.n_games),
                      !(d.n_games)));
    }
    var diag = (fh && fh.diagnosis) ? String(fh.diagnosis) : "";
    // RED IS FOR THE FEED THAT PRICES THE BOARD. With CLV retired the absence
    // of a close capture is not a fault, so it no longer reddens the strip; a
    // missing OPEN snapshot still does, because that one empties the page.
    var feedBad = clvEnabled() ? (!fh || !fh.n_slates_with_close)
                               : !(d && d.status && d.status.odds_captured_at);
    host.className = "bt-fh" + (feedBad ? " bt-fh-red" : "");
    host.setAttribute("role", "status");
    host.innerHTML = '<div class="bt-fh-line"' +
      (diag ? ' title="' + esc(diag) + '"' : "") + ">" +
      '<span class="bt-fh-hd">FEED</span>' + segs.join("") +
      (clvEnabled() && fh && !fh.n_slates_with_close
        ? '<span class="bt-fh-note">no close snapshot, so no ' + selNoun() +
          " here can be graded against the closing line</span>"
        : "") + "</div>";
  }

  // ---- model banner ---------------------------------------------------------
  function renderBanner() {
    renderFeedHealth();
    var host = el("betting-banner");
    if (!host) return;
    if (!S.data) {
      host.innerHTML = '<div class="bt-asof">Model payload not loaded. Calculators and ' +
        "My Bets still work.</div>";
      return;
    }
    var m = S.data.model || {}, st = S.data.status || {};
    var v = vstate();
    var chips = [];
    // THE STAGE CHIP IS THE ONLY CONVERSION ROUTE ON THIS PAGE, so it is a
    // link. Before this it was inert text: a reader who wanted to know what
    // "Diamond preview" meant had to find the last item of a nav dropdown. The
    // chip keeps its own class, so it still reads as a chip rather than as body
    // copy with an underline.
    chips.push('<a class="bt-chip bt-chip-stage bt-chip-link" href="/diamond/" ' +
      'title="Diamond: what it is and what it costs">' +
      esc(m.stage || "Diamond preview") + "</a>");
    chips.push('<span class="bt-chip ' + (m.validated ? "bt-chip-ok" : "bt-chip-warn") + '">' +
      (m.validated ? "validated" : "unvalidated model") + "</span>");
    // Which mode the numbers on this page came from, on every tab. The word
    // "unvalidated" on its own does not tell a reader that the Brier he is
    // looking at was scored on features that contain the game.
    if (v && v.available !== false && v.headline_mode) {
      chips.push('<span class="bt-chip bt-chip-warn">' + esc(v.headline_mode) + " numbers</span>");
      var vin = v.vintage || {};
      if (vin.min_graded_games_for_min_edge != null) {
        chips.push('<span class="bt-chip bt-chip-warn">vintage graded ' +
          (vin.n_graded == null ? "-" : vin.n_graded) + " of " +
          vin.min_graded_games_for_min_edge + "</span>");
      }
    }
    if (boardClock().all) {
      chips.push('<span class="bt-chip bt-chip-warn">prices historical</span>');
    } else {
      chips.push('<span class="bt-chip ' + (st.odds_feed === "ok" ? "bt-chip-ok" : "bt-chip-warn") + '">' +
        (st.odds_feed === "ok" ? "odds feed live" : "no odds feed") + "</span>");
    }
    if (gated()) {
      chips.push('<a class="bt-chip bt-chip-warn bt-chip-link" href="/diamond/">preview slice</a>');
    }
    host.innerHTML = '<div class="bt-asof">' +
      esc(S.data.slate_date || "") + " slate &middot; " + (S.data.n_games || 0) +
      " games priced &middot; " + chips.join(" ") + "</div>" + staleLine();
    wireGl(host);
  }

  // ---- section: the two published slots -------------------------------------
  // THE SLOTS ARE DECLARED, NOT HARD-CODED INTO THE RENDERER, so a third slot
  // added server-side needs one row here and inherits the badge, the sentence
  // and the empty state rather than a new copy of all three.
  // Each slot carries BOTH frames' copy; slotTitle/slotLead pick per the
  // served frame, preferring the payload's own slot_label so the page can
  // never disagree with the server about what a slot is called.
  var SLOTS = [
    { key: "pick_of_the_day",
      pickTitle: "Pick of the Day",
      watchTitle: "Model Watch: largest disagreement",
      pickLead: "Highest model confidence inside the standard price band, any priced market.",
      watchLead: "Largest gap between the model and the de-vigged market inside the " +
                 "standard price band, any priced market. Logged in public, not a " +
                 "recommendation." },
    { key: "longshot_of_the_day",
      pickTitle: "Longshot Value of the Day",
      watchTitle: "Model Watch: long-price disagreement",
      pickLead: "Best expected value at a long price. Loses most nights.",
      watchLead: "Largest expected-value gap at a long price. Loses most nights. " +
                 "Logged in public, not a recommendation." }
  ];

  function slotTitle(slot) {
    var m = slotMeta(slot.key);
    if (m && m.slot_label) return m.slot_label;
    var p = S.data && S.data[slot.key];
    if (p && p.slot_label) return p.slot_label;
    return watchMode() ? slot.watchTitle : slot.pickTitle;
  }
  function slotLead(slot) {
    return watchMode() ? slot.watchLead : slot.pickLead;
  }

  // The per-slot block of `pick_meta`, with the top-level block as the fallback
  // for a payload built before the slots existed. Returning the top level is
  // safe here because the fields the callers read (provisional, min_edge,
  // basis) have the same meaning at both levels; what the older shape cannot
  // supply is the slot's own reason, and the callers check for that.
  function slotMeta(key) {
    var m = (S.data && S.data.pick_meta) || {};
    return ((m.slots || {})[key]) || m;
  }

  // The one guard on a null floor, and since 2026-08-16 the one renderer of
  // the floor phrase anywhere on the page. Two of the four floor renderings
  // used to call pct(m.min_edge) raw and printed a bare hyphen where a
  // percentage belongs the day min_edge arrives null. The article is baked in
  // here because the null phrase carries its own.
  function floorText(m) {
    if (!m || m.min_edge == null) return "the minimum edge";
    return "a " + pct(m.min_edge, 1) + (m.provisional === false ? " measured threshold"
                                                                : " policy floor");
  }

  // The badge that carries the whole labelling contract. Before this it existed
  // only in the payload: `provisional` appeared nowhere in this file, so the
  // flag every surface was supposed to key its labelling off never reached a
  // reader. A pick shown without it reads as a recommendation the site stands
  // behind, which is the one outcome the module was built to prevent.
  function provBadge(m) {
    if (!m || m.provisional === false) return "";
    return '<span class="bt-tag bt-tag-warn bt-prov" title="' +
      esc("Cleared a policy floor, not a measured threshold. The model is " +
          "unvalidated.") + '">provisional</span>';
  }

  // The sentence a reader who does not know what a de-vigged probability is can
  // still act on. Built entirely from served fields; it computes nothing.
  function pickSentence(p) {
    var s = fmtOdds(p.odds) + " " + gl("implies", "implied_probability") + " " +
      (p.implied_prob != null ? pct(p.implied_prob, 1) + ", " : "") +
      pct(p.market_fair_prob, 1) + " after the " + gl("vig", "vig") + ". " +
      gl("Edge", "bet_edge") + " is model minus market fair.";
    return "<p>" + s + "</p>";
  }

  function unitLine(p, m) {
    var bits = [];
    bits.push("Shown at " + num(p.suggested_units == null ? p.stake_units
                                                          : p.suggested_units, 1) +
      "u flat; recorded at " + num(p.stake_units, 1) + "u like every row, because " +
      "variable stakes cannot be audited.");
    var kq = (p.kelly_quarter != null) ? p.kelly_quarter
      : (p.kelly_full != null ? p.kelly_full / 4 : null);
    var chipHtml = (kq == null) ? "" :
      '<span class="bt-numchip bt-numchip-info"><span class="bt-numchip-l">Quarter ' +
      gl("Kelly", "kelly_criterion") + '</span><span class="bt-numchip-v">' +
      pct(kq, 1) + "</span></span>";
    return "<p>" + bits.join(" ") + " " + gl("Kelly", "kelly_criterion") +
      " is informational, never a stake: it assumes the probability is right.</p>" +
      (chipHtml ? '<div class="bt-pick-nums">' + chipHtml + "</div>" : "") +
      (m && m.provisional !== false
        ? note(gl("Provisional " + selNoun(), "provisional_pick") +
               ": cleared " + floorText(m) + " because the model is unvalidated. " +
               "Not advice.")
        : "");
  }

  // A WHOLE-NUMBER TOTAL REFUNDS SOME OF THE TIME, and the page said nothing.
  // `p_push` is the model's own mass exactly on the line, served on the row;
  // the two sides beside it are already conditional on it not landing. The
  // served EV carries the (1 - p_push) factor, so this line is what makes that
  // number legible rather than a discount nobody can see the reason for.
  // 2026-08-16: the sentence used to say "the expected value above" while
  // pickCard renders the EV chip below it, and the disclosure existed on the
  // two pick cards only while the team board rendered the same push-discounted
  // EV and push-conditional model probability in silence. The text is built
  // here for both surfaces, each naming where its own numbers actually sit.
  function pushText(p, probName, evName) {
    if (!p || p.p_push == null || !(p.p_push > 0)) return "";
    var pt = (p.point != null) ? p.point : null;
    var whole = (pt != null && Math.abs(pt - Math.round(pt)) < 1e-9);
    if (!whole) return "";
    return esc(String(Math.round(pt))) + " is a push " + pct(p.p_push, 1) +
      " of the time. A push returns the stake, so " +
      (probName || "the model probability") + " is the chance to cash given " +
      "the bet resolves, and " + (evName || "the expected value below") +
      " is that conditional value scaled by the " + pct(1 - p.p_push, 1) +
      " that resolve.";
  }
  function pushLine(p) {
    var t = pushText(p, null, null);
    return t ? "<p>" + t + "</p>" : "";
  }

  // THE MARGIN MODEL, NAMED ON THE PICK. The Poisson difference is the wrong
  // distribution for run scoring, a one-parameter correction was fitted and
  // pre-registered against a held-out gate, and the gate's verdict decides
  // whether the price a reader is looking at came from one or the other. The
  // verdict is READ; nothing about it is written down in this file.
  function dispersionLine(load) {
    var dr = ((load ? aux("evald") : AUX.evald) || {}).run_dispersion || null;
    if (!dr) return "";
    var verdict = esc(String(dr.verdict || dr.status || "unknown"));
    if (dr.served) {
      return note("Margin model: the run-dispersion correction is SERVED at alpha " +
        num(dr.served_alpha, 5) + ". Gate verdict " + verdict + ".");
    }
    return note("Margin model: the " + gl("dispersion correction", "run_dispersion") +
      " (alpha " + num(dr.alpha, 5) + ") returned <strong>" + verdict +
      "</strong> at its pre-registered gate and is NOT served. This price is the " +
      "Poisson difference, which underweights the tails. Grid on the Validation tab.");
  }

  // WHICH LEG BARS, READ RATHER THAN INFERRED (owner decision 2026-09-17, O15).
  //
  // `betting_model.SLOT_MARKET_POLICY` has THREE registered values and a
  // fail-closed fourth state for an unregistered string, so comparing it to one
  // name cannot answer "does this leg bar a slot". This file used to do exactly
  // that: it compared `slot_market_policy` against the single value "any", which
  // is why its both-legs copy read "clearing one leg does not reopen the
  // market" under `ledger_gated`, where clearing the LEDGER leg alone reopens it.
  //
  // The server derives the pair once, in `betting_export.slot_market_policy_legs`,
  // and publishes it twice: on `market_publishability.policy` as
  // `ledger_leg_bars` / `dispersion_leg_bars`, and on
  // `pick_meta.market_policy_legs` as `ledger_bars` / `dispersion_bars`. This
  // reads whichever is present and NEVER re-derives the rule from the policy
  // name: a page that re-implements a server rule is a second reading of one
  // constant, and the two would drift on the day a fourth value lands.
  //
  // `known` is false only for a payload written before those fields existed.
  // The copy then says which legs are CLOSED, which such a payload does carry,
  // and stops short of saying which of them can refuse a slot.
  function policyLegs() {
    var d = S.data || {};
    var pol = (d.market_publishability || {}).policy || {};
    var pm = (d.pick_meta || {}).market_policy_legs || {};
    var led = (typeof pol.ledger_leg_bars === "boolean") ? pol.ledger_leg_bars
      : ((typeof pm.ledger_bars === "boolean") ? pm.ledger_bars : null);
    var dis = (typeof pol.dispersion_leg_bars === "boolean") ? pol.dispersion_leg_bars
      : ((typeof pm.dispersion_bars === "boolean") ? pm.dispersion_bars : null);
    var name = pol.slot_market_policy || (d.pick_meta || {}).market_policy || null;
    // THE OWNER-DECISION RECEIPT, READ RATHER THAN HARD-WRITTEN. The served
    // note beside the policy ends "(owner decision 2026-09-05, docs/diamond-
    // betting.md 7d)" and carries the date of whichever value is in force. The
    // both-legs sentence has printed that date since the any-market decision
    // shipped, so taking it off the note keeps the receipt on the page without
    // welding it to one value: a note with no date simply prints none.
    var rc = /owner decision (\d{4}-\d{2}-\d{2})/.exec(
      String(pol.slot_market_policy_note || ""));
    return {
      known: (led !== null && dis !== null),
      ledger: led, dispersion: dis,
      bars: (led === true || dis === true),
      // The served string, printed verbatim where it is printed at all. The
      // page names the policy; it never decides anything from the name.
      name: name,
      receipt: rc ? (" (" + rc[1] + ")") : "",
      phrase: name ? (" under the " + esc(name) + " slot market policy") : ""
    };
  }

  // THE BOTH-LEGS COPY STATE (2026-08-19, pre-decided; repaired 2026-09-18). A
  // market can be watch-only twice over: the theory leg (the margin-shape
  // exclusion, its gate indeterminate) and the evidence leg (the market's own
  // graded record resolved worse than a coin at the canonical-game floor). When
  // the payload says both legs closed a market, the page states ONE combined
  // state with BOTH numbers, every one of them read off market_publishability.
  // Nothing here is hand-written: the t, the bar, the Brier, the game count and
  // the floor all ride the payload, so the copy moves the night the numbers do.
  // WHICH of the two closed legs can refuse a slot comes from `policyLegs`, so
  // the sentence is true under every value the policy can take and not only
  // under the one shipped today.
  //
  // FOUR STATES ARE WRITTEN AND THREE ARE REACHABLE TODAY.
  // `betting_export.slot_market_policy_legs` maps "any" to (theory False,
  // evidence False), "ledger_gated" to (False, True) and every other string,
  // registered or not, to (True, True), so a theory leg that bars ALWAYS comes
  // with an evidence leg that bars: the theory-leg-only branch cannot render
  // off a payload the server writes. It is written anyway, because the day a
  // fourth registered value lands the alternative is this page falling through
  // to a branch whose sentence nobody checked. A fifth state covers a payload
  // written before the two booleans existed.
  function marketGateNotes() {
    var mp = (S.data || {}).market_publishability || null;
    if (!mp || !mp.markets) return "";
    var pol = mp.policy || {};
    var pl = policyLegs();
    var out = [];
    Object.keys(mp.markets).forEach(function (k) {
      var m = mp.markets[k] || {};
      if (!m.both_legs) return;
      var lg = m.ledger_leg || {};
      var floor = (pol.n_min == null) ? "the canonical-game floor"
        : ("the n of " + pol.n_min + " floor");
      var bar = (pol.z == null) ? "the one-sided 95% bar"
        : ("the " + num(pol.z, 3) + " one-sided bar");
      var state, tail;
      if (!pl.known) {
        state = "is closed on both legs";
        tail = ". This payload does not say which leg can refuse a slot, so " +
          "which of them would have to clear is not stated here; the shadow " +
          "and calibration ledgers keep recording it.";
      } else if (pl.ledger && pl.dispersion) {
        state = "is watch-only for two independent reasons";
        tail = ". Clearing one leg does not reopen the market; the shadow and " +
          "calibration ledgers keep recording it.";
      } else if (pl.ledger) {
        state = "is watch-only: its evidence leg bars it" + pl.phrase + pl.receipt;
        tail = ". Clearing the evidence leg reopens it, because the theory leg " +
          "rides a published row as disclosure and bars nothing here; the " +
          "shadow and calibration ledgers keep recording it.";
      } else if (pl.dispersion) {
        state = "is watch-only: its theory leg bars it" + pl.phrase + pl.receipt;
        tail = ". Clearing the theory leg reopens it, because the evidence leg " +
          "rides a published row as disclosure and bars nothing here; the " +
          "shadow and calibration ledgers keep recording it.";
      } else {
        // BYTE FOR BYTE THE SENTENCE THE PAGE HAS PRINTED SINCE 2026-09-05,
        // with the policy name and the decision date READ off the payload
        // instead of hard-written. Under "any" this renders the identical
        // words, which is what lets this repair claim it moved no served copy:
        // a correctness fix that also reworded a shipped sentence would have
        // been two changes wearing one commit message.
        state = "carries two independent cautions; eligible under the " +
          esc(pl.name || "current") + "-market policy" + pl.receipt;
        tail = ". Both ride any published row on this market as disclosure; the " +
          "shadow and calibration ledgers keep recording it.";
      }
      out.push(note("<strong>The " + esc(k) + " market " + state + ".</strong>" +
        " Theory leg: " +
        esc((m.dispersion_leg || {}).reason ||
            "the margin-shape exclusion bars this market") +
        ". Evidence leg: its graded record resolved worse than a coin at " +
        floor + ", mean Brier " + num(lg.brier, 5) + " on " +
        (lg.n_games == null ? "an unreported count of" : lg.n_games) +
        " canonical games, t " + num(lg.t, 3) + " against " + bar + tail));
    });
    // ONE LEG, AND IT BARS: the gap the block above left open (named by the
    // 7d follow-ups, closed 2026-09-18). Everything above fires only where
    // BOTH legs closed a market. A market closed on ONE leg fills no slot
    // either, whenever that leg is one the policy lets bar, and the page said
    // nothing at all about it. On HEAD's payload the runline is theory-closed
    // with its evidence leg open, which under "dispersion_gated" is barred and
    // silent.
    //
    // THE TEST IS THE SERVED ANSWER. `publishable` is computed by the server
    // with the policy already folded in, so this page re-derives no rule; the
    // leg blocks name WHICH leg closed it and `policyLegs` says whether that
    // leg bars. Where no leg bars, every market is publishable and this loop
    // prints nothing, which is why it moves no copy on today's board.
    if (pl.bars) {
      Object.keys(mp.markets).forEach(function (k) {
        var m = mp.markets[k] || {};
        if (m.both_legs || m.publishable !== false) return;
        var theoryClosed = (m.dispersion_leg || {}).publishable === false;
        var ledgerClosed = (m.ledger_leg || {}).status === "ledger_closed";
        var byTheory = theoryClosed && pl.dispersion === true;
        var byLedger = ledgerClosed && pl.ledger === true;
        if (!byTheory && !byLedger) return;
        var closed = byTheory ? "theory" : "evidence";
        var open = byTheory ? "evidence" : "theory";
        out.push(note("<strong>The " + esc(k) + " market fills no " + selNoun() +
          " slot" + pl.phrase + pl.receipt + ": its " + closed +
          " leg bars it.</strong> " +
          esc(sentence(m.reason) || "The payload gives no reason.") +
          ". Its " + open + " leg is open, and the shadow and calibration " +
          "ledgers keep recording this market."));
      });
    }
    return out.join("");
  }

  // THE SLOT'S OWN SETTLED RECORD (2026-08-16). The watch framing is only
  // honest if the card carries what this selection rule has actually done:
  // the server reads betting_shadow.summary() by tag and serves it on the
  // slot meta, so "this rule is 2-4, -47.9%" costs no second fetch. Small
  // samples are labelled against the same 100-row floor gate 3 sweeps at.
  function tagRecordLine(key, m) {
    var tr = (m && m.tag_record) ||
             ((S.data && S.data[key]) || {}).tag_record || null;
    if (!tr || tr.available === false) return "";
    if (!tr.n_settled) {
      return '<div class="bt-tagrec">Selection rule ' + esc(tr.tag || "") +
        ": no settled paper bets yet.</div>";
    }
    var rec = tr.won + "-" + tr.lost + (tr.push ? "-" + tr.push : "");
    var units = (tr.net_units == null) ? "" : signed(tr.net_units, 1) + "u, ";
    var roi = (tr.roi == null) ? "ROI not computable" : pct(tr.roi, 1) + " ROI";
    var small = tr.small_n
      ? ' <span class="bt-tag bt-tag-warn">small sample: ' + tr.n_settled +
        " settled of the " + (tr.sweep_floor || 100) + " the sweep needs</span>"
      : "";
    return '<div class="bt-tagrec">Selection rule ' + esc(tr.tag || "") +
      ": <strong>" + rec + "</strong> on settled paper bets, " + units +
      roi + "." + small + "</div>";
  }

  // The board rows behind one slot row, so the worked example prices the same
  // market the reader is looking at rather than recomputing anything private.
  function marketRowsFor(p) {
    var bets = (S.data || {}).team_bets || [];
    for (var i = 0; i < bets.length; i++) {
      var b = bets[i];
      if (b.game_pk !== p.game_pk) continue;
      if (p.market === "moneyline") return b.moneyline || null;
      if (p.market === "runline") return b.runline || null;
      if (p.market === "total") return (b.total || {}).sides || null;
    }
    return null;
  }

  // THE WORKED DE-VIG (2026-08-16). The watch card frames the slot as a
  // disagreement, and a disagreement is only legible if the reader can see
  // what it is measured against. Every number here is computed from the
  // served rows with the same primitives the calculators use: raw implied =
  // 1/decimal per side, the overround is their sum minus one, the fair
  // probability splits it proportionally, and the edge is model minus fair.
  function devigExample(p) {
    var rows = marketRowsFor(p);
    if (!rows || rows.length < 2) return "";
    var decs = rows.map(function (r) {
      return (r.decimal != null) ? Number(r.decimal) : amToDec(r.odds);
    });
    if (decs.some(function (x) { return !x || x <= 1; })) return "";
    var raws = decs.map(decToImplied);
    var sum = 0;
    raws.forEach(function (q) { sum += q; });
    if (!sum) return "";
    var idx = -1;
    rows.forEach(function (r, i) {
      if (idx !== -1) return;
      if (r.side !== p.side) return;
      if (r.point != null && p.point != null &&
          Number(r.point) !== Number(p.point)) return;
      idx = i;
    });
    if (idx === -1) return "";
    var fair = raws[idx] / sum;
    var lines = rows.map(function (r, i) {
      return "<li>" + esc(r.label || r.side || "") + " at " + fmtOdds(r.odds) +
        " implies " + pct(raws[i], 1) + " raw</li>";
    }).join("");
    var servedGap = (p.market_fair_prob != null &&
                     Math.abs(fair - p.market_fair_prob) > 0.001)
      ? "<p>The served fair (" + pct(p.market_fair_prob, 1) + ") is de-vigged from " +
        "ONE book's two-sided quote; the best prices above can come from different " +
        "books, so the two fair numbers can differ. The edge uses the served one.</p>"
      : "";
    return '<details class="bt-devigex"><summary class="bt-devigex-sum">' +
      "Worked " + gl("de-vig", "devig") + "</summary>" +
      '<div class="bt-devigex-body">' +
      "<p>Implied probability = 1 / decimal odds:</p>" +
      '<ul class="bt-list">' + lines + "</ul>" +
      "<p>Sum " + pct(sum, 1) + "; the " + pct(sum - 1, 1) + " over 100% is the " +
      gl("overround", "vig") + ". Split proportionally, " +
      esc(p.label || p.side || "this side") + " is fair at " + pct(fair, 1) +
      ". Model " + pct(p.model_prob, 1) + ", so the " + gl("edge", "bet_edge") +
      " is " + signed((p.model_prob - fair) * 100, 1) + " points.</p>" + servedGap +
      "</div></details>";
  }

  // ---- Dugout context (In-Game Management), beside the price and in none of it ----
  // Rendered from S.data.dugout_context only. Reads no priced key, moves no number,
  // and prints the payload's own not-priced sentence in every block it draws. Every
  // sentence a reader sees comes from the payload; the client types only the glue
  // words "Family" and "n" and the league parenthetical. No plus suffix, no tier
  // class, no ladder, no sign colour: a z prints with its leading sign in neutral
  // ink, because beside a price a green number reads as a signal. The block is a
  // <details> closed by default at the FOOT of the card, after every priced cell.
  function dugoutCtx() { return (S.data && S.data.dugout_context) || null; }

  function dugoutFill(tpl, vars) {
    return String(tpl || "").replace(/\{(\w+)\}/g, function (m, k) {
      return (vars && vars[k] != null) ? String(vars[k]) : m;
    });
  }

  function dugoutBlock(gamePk) {
    var ctx = dugoutCtx();
    if (!ctx || ctx.status !== "built") return "";        // dark: the section note says why
    var g = ctx.games && ctx.games[String(gamePk)];
    if (!g) return "";
    return '<details class="bt-dugout"><summary class="bt-details-sum bt-dugout-sum">' +
      esc(ctx.head) + ": " + esc(g.away) + ", " + esc(g.home) + "</summary>" +
      '<div class="bt-dugout-body">' +
      '<p class="bt-dugout-np">' + esc(ctx.not_priced_sentence) + "</p>" +
      '<div class="bt-dugout-clubs">' + dugoutClub(g.away, ctx) + dugoutClub(g.home, ctx) + "</div>" +
      '<p class="bt-dugout-fine">' + esc(ctx.style_sentence) + "</p>" +
      '<p class="bt-dugout-fine">' + esc(ctx.realized_sentence) + " " + esc(ctx.agent_sentence) + "</p>" +
      '<p class="bt-dugout-fine">' + esc(ctx.overlap_note) + "</p>" +
      '<p class="bt-dugout-src">' + esc(ctx.source_label) + "</p>" +
      "</div></details>";
  }

  function dugoutDarkNote() {
    var ctx = dugoutCtx();
    if (!ctx || ctx.status === "built") return "";
    return '<div class="bt-note bt-dugout-dark">' + esc(ctx.head) + ": " +
      esc(ctx.blocker || "") + " " + esc(ctx.not_priced_sentence) + "</div>";
  }

  function dugoutClub(org, ctx) {
    var c = (ctx.clubs || {})[org];
    var head = '<div class="bt-dugout-org">' + teamLogo(org) + " " + esc(org) + "</div>";
    if (!c || c.row_note || !c.style) {
      return '<div class="bt-dugout-club">' + head +
        '<p class="bt-dim">' + esc((c && c.row_note) || ctx.season_note || "") + "</p>" +
        dugoutLink(c, org) + "</div>";
    }
    var zs = (ctx.style_columns || []).map(function (col) {
      return '<span class="bt-dugout-z" title="' + esc(col.basis) + '">' +
        '<span class="bt-dugout-zl">' + gl(col.label, col.key.replace("z_", "") + "_z") + "</span>" +
        '<span class="bt-dugout-zv">' + esc(signed(c.style[col.key], 1)) + "</span></span>";
    }).join("");
    var rates = (ctx.rate_columns || []).map(function (col) {
      return "<tr><td class=\"bt-l\">" + esc(col.label) + "</td><td>" +
        esc(num((c.rates || {})[col.key], col.decimals)) + "</td></tr>";
    }).join("");
    var sh = c.shape || {};
    var shape = "<tr><td class=\"bt-l\">Hook, median pitches (league " +
      esc(num(sh.league_hook_median_pitches, 0)) + ")</td><td>" +
      esc(num(sh.hook_median_pitches, 0)) + "</td></tr>" +
      "<tr><td class=\"bt-l\" colspan=\"2\"><span class=\"bt-dim\">" +
      esc(sh.li_at_entry_blocker || ctx.shape_dark_sentence || "") + "</span></td></tr>";
    var realized = (ctx.realized_families || []).map(function (f) {
      var v = (c.realized || {})["mwpa_" + f.key], n = (c.counts || {})["n_" + f.key];
      var cell = (v == null)
        ? '<span class="bt-dim">' + esc("- " + dugoutFill(ctx.below_floor_template,
                                                          {floor: f.floor, n: (n == null ? "-" : n)})) + "</span>"
        : esc(signed(v, 3));
      return "<tr><td class=\"bt-l\">" + esc(f.label) + "</td><td>" +
        esc(n == null ? "-" : n) + "</td><td>" + cell + "</td></tr>";
    }).join("");
    return '<div class="bt-dugout-club">' + head +
      '<div class="bt-dugout-hd">' + esc(ctx.style_head) + "</div>" +
      '<div class="bt-dugout-zs">' + zs + "</div>" +
      '<div class="bt-dugout-hd">' + esc(ctx.rates_head) + "</div>" +
      '<table class="bt-dugout-t"><tbody>' + rates + "</tbody></table>" +
      '<div class="bt-dugout-hd">' + esc(ctx.shape_head) + "</div>" +
      '<table class="bt-dugout-t"><tbody>' + shape + "</tbody></table>" +
      '<div class="bt-dugout-hd">' + esc(ctx.realized_head) + "</div>" +
      '<div class="bt-scroll mlbstats-scroll"><table class="bt-dugout-t"><thead><tr>' +
      '<th class="bt-l">Family</th><th>n</th><th>' + gl("mWPA", "realized_mwpa") +
      "</th></tr></thead><tbody>" + realized + "</tbody></table></div>" +
      // the units sentence of the board sits under the table, not inside the
      // header cell, so the column reads as one word at 390 and the unit stays
      // visible on a touch screen (a title attribute never opens there)
      '<p class="bt-dugout-fine">' + esc("mWPA: " + ((ctx.units || {}).mwpa || "")) + "</p>" +
      dugoutLink(c, org) + "</div>";
  }

  function dugoutLink(c, org) {
    var href = (c && c.link) || ("/management/#section=clubs&team=" + org);
    var label = (c && c.link_label) || ("Open " + org + " on In-Game Management");
    return '<a class="bt-link bt-dugout-link" href="' + esc(href) + '">' + esc(label) + "</a>";
  }

  function pickCard(slot) {
    var d = S.data;
    var p = d[slot.key];
    var m = slotMeta(slot.key);
    var hd = '<div class="bt-pick-hd">' + esc(slotTitle(slot)) + " " +
      provBadge(m) + "</div>";
    if (!p) {
      // THE HONEST EMPTY STATE. It names the floor it could not clear, and it
      // says the floor is not lowered to fill the slot, because a threshold
      // invented to make a selection appear is the single most dishonest
      // number this module could publish.
      var why = (m && m.reason) || d.pick_reason || "";
      return '<div class="bt-pick bt-pick-empty">' + hd +
        pxState("empty", '<div class="bt-pick-sel bt-dim">Nothing qualifies today</div>' +
        "<p>" + esc(why) + "</p>" +
        "<p>The floor is " + floorText(m) + ", the same for every slot, and it is " +
        "never lowered to make a " + selNoun() + " appear.</p>") + "</div>";
    }
    // THE REDACTED SLOT (D16). The preview slice keeps the whole trust surface
    // (validation state, record, publish blockers) and withholds the SELECTION
    // only: market and floor, no side, no price, no book, no numbers. That is
    // the only shape in which a gate can exist without the free tier losing the
    // ability to check the process, and it is why the redaction is a server
    // rewrite rather than a client that hides fields it was sent.
    if (p.redacted) {
      return '<div class="bt-pick bt-pick-redacted">' + hd +
        "<p class=\"bt-pick-lead\">" + esc(slotLead(slot)) + "</p>" +
        '<div class="bt-pick-sel bt-dim">Selection withheld</div>' +
        '<div class="bt-pick-meta">' + esc(p.market || "market not stated") +
        " &middot; cleared " + (p.min_edge_used == null ? "the floor"
                                                        : pct(p.min_edge_used, 1)) +
        "</div>" +
        "<p>" + esc(p.redaction_note || ("Filled. The preview slice shows the market " +
          "and the floor it cleared; the side, price and book are withheld.")) + "</p>" +
        note("Never gated: the validation state, the clocks, the gate table and the " +
          "public record.") + "</div>";
    }
    // THE CAVEAT SLOT CARRIES BOTH LINES. The row's own caveat says the market
    // is one of the two the margin model is worst at; the dispersion line says
    // what was done about that and what the gate returned.
    var shaped = (p.market === "runline" || p.market === "total");
    // L14-01: a runline slot also carries what the model's tie after nine is
    // worth to it. The sentence is built server-side from the row's own
    // tie_atom block, so no number here is typed or recomputed.
    // BET1: a total slot on a slate whose totals lean one way carries the
    // server's sentence about that lean, built from the payload's own block.
    var caveat = (postseasonLabel(p)
        ? note("<strong>Postseason game: " + esc(postseasonLabel(p)) + ".</strong> " +
          "Every game behind the model's evidence is a regular-season game; " +
          "pricing the postseason is an owner decision of 2026-10-01, and this " +
          "row is recorded in the postseason sub-ledger.")
        : "") +
      (p.caveat ? note(esc(p.caveat)) : "") +
      (p.tie_atom_caveat ? note(esc(p.tie_atom_caveat)) : "") +
      (p.total_level_caveat ? note(esc(p.total_level_caveat)) : "") +
      (p.evidence_caveat ? note(esc(p.evidence_caveat)) : "") + dispersionLine(shaped);
    // The watch additions render in the watch frame only: when the gates open
    // the pick rendering returns exactly as it was, which is the self-lift the
    // 2026-08-16 decision requires.
    var watchBits = watchMode()
      ? tagRecordLine(slot.key, m) + devigExample(p)
      : "";
    var pastGame = ((d.team_bets || []).filter(function (b) {
      return b && p.game_pk != null && b.game_pk === p.game_pk;
    })[0]);
    var past = !!(pastGame && gameStarted(pastGame));
    return '<div class="bt-pick' + (past ? " bt-pick-past" : "") + '">' + hd +
      (past ? note("<strong>This game has started.</strong> The price below was " +
        "pregame and is no longer on offer.") : "") +
      "<p class=\"bt-pick-lead\">" + esc(slotLead(slot)) + "</p>" +
      '<div class="bt-pick-sel">' + esc(p.label || p.side || "") + " " +
      fmtOdds(p.odds) + "</div>" +
      '<div class="bt-pick-meta">' + esc(p.matchup || "") + " &middot; " +
      esc(p.market || "") + " &middot; " + esc(p.book || "") + postseasonTag(p) + "</div>" +
      pickSentence(p) + pushLine(p) +
      '<div class="bt-pick-nums">' +
      chip("Model", pct(p.model_prob)) + chip("Market fair", pct(p.market_fair_prob)) +
      chip("Edge", signed(p.edge * 100, 1) + "%") +
      chip("EV / unit", signed(p.ev_per_unit, 3)) + "</div>" +
      watchBits + caveat + unitLine(p, m) + dugoutBlock(p.game_pk) + "</div>";
  }

  // AN EMPTY BOARD IS A MEASUREMENT, NOT AN OUTAGE, and it has to read as one.
  // The census counts what the selection rule actually saw: every side on the
  // board with a real taken price, how many of those cleared the floor, and how
  // many survived the price band. All three are counted off the SERVED rows
  // with the same two conditions `_floor_clearing_sides` uses (an odds value
  // and a book), so the count on screen is the count the server ranked.
  function pricedSideCount(bets) {
    var n = 0;
    (bets || []).forEach(function (b) {
      [b.moneyline, b.runline, (b.total || {}).sides].forEach(function (rows) {
        (rows || []).forEach(function (r) {
          if (r && r.odds != null && r.book) n += 1;
        });
      });
    });
    return n;
  }

  // THE CENSUS HAS TWO DENOMINATORS AND USED ONLY ONE (repaired 2026-09-18).
  // `pick_meta.n_floor_clearing_sides` is policy-filtered at seam 1, so under a
  // gated policy it counts "cleared the floor AND the policy lets it fill a
  // slot" while this sentence prints it under the words "cleared the floor".
  // The server publishes the unfiltered count beside it as
  // `n_floor_clearing_sides_before_policy` for exactly this read. The floor
  // clause now takes that one, and the ranked count is named only when the two
  // differ, so the sentence says what it counts under every policy value. Where
  // no leg bars, the two are equal and this renders word for word as it did.
  function pickCensus() {
    var d = S.data || {};
    var meta = d.pick_meta || {};
    if (meta.blocked) {
      return note("<strong>Nothing was ranked.</strong> " +
        esc(meta.blocked_reason || "the selection rule never ran") + ".");
    }
    var n = pricedSideCount(d.team_bets);
    var ranked = meta.n_floor_clearing_sides;
    var cleared = (meta.n_floor_clearing_sides_before_policy == null)
      ? ranked : meta.n_floor_clearing_sides_before_policy;
    var gated = (cleared != null && ranked != null && ranked !== cleared)
      ? (", " + ranked + " of those are on a market the slot policy lets fill a " +
         selNoun() + " slot,")
      : ",";
    var band = ((meta.slots || {}).pick_of_the_day || {}).band || "the price band";
    var floor = (meta.min_edge == null) ? "the floor" : pct(meta.min_edge, 1);
    return note("<strong>Census.</strong> " + n + " sides priced across " +
      (d.n_games || 0) + " games, " +
      (cleared == null ? "an unreported number of" : cleared) +
      " cleared the " + esc(floor) + " floor" + gated + " and none of those are inside " +
      esc(band) + ". A measurement of tonight's board, not a failure to load one; " +
      "the floor was not lowered.");
  }

  function renderPick() {
    var d = S.data;
    var out = [];
    if (!d) {
      return empty((watchMode() ? "Model Watch" : "Pick of the day") + " is unavailable",
        "The betting payload has not been built yet.");
    }
    var any = SLOTS.some(function (s) { return !!d[s.key]; });
    out.push(SLOTS.map(pickCard).join(""));
    // A market closed by BOTH legs never reaches a slot card, so its copy
    // state renders here at market level or nowhere.
    out.push(marketGateNotes());
    // Dugout context dark state, once, at section level (a built block renders
    // on the filled slot cards themselves; the redacted and empty slots carry none).
    out.push(dugoutDarkNote());

    if (!any) out.push(pickCensus());
    if (!any) {
      // EVERY blocker, not the first one. The payload used to carry a single
      // reason, so on a day with no odds feed the page said "no odds feed" and
      // a reader walked away thinking an API key was the only thing missing.
      var blockers = d.pick_blockers || [];
      var lines = blockers.length
        ? '<ul class="bt-list">' + blockers.map(function (b) {
            var reason = String(b.reason || "");
            // The need is appended only when the reason has not already said
            // it, so the min_edge line does not print "600 vintage-graded
            // games" twice in one bullet.
            var tail = (b.need && reason.indexOf(String(b.need)) === -1)
              ? ' <span class="bt-dim">(needs ' + esc(b.need) + "; has " +
                esc(haveText(b)) + ")</span>"
              : "";
            return "<li>" + esc(reason) + tail + "</li>";
          }).join("") + "</ul>"
        : "<p>" + esc(d.pick_reason || "") + "</p>";
      out.push('<div class="bt-nopick"><div class="bt-nopick-hd">Why nothing is here' +
        "</div><p>" + esc(noPickHeadline(vstate())) + "</p>" + lines + "</div>");
    }

    // THE PANELS ARE COLLAPSED, NOT REMOVED. Every word of the contamination
    // account, the gate table and the backtest is still here, one click away
    // and summarised in a sentence above the toggle. Leading a casual reader
    // straight into it taught him nothing; hiding it would be dishonest. This
    // is the only arrangement that is neither.
    out.push(trustTopline());
    out.push('<details class="bt-details"><summary class="bt-details-sum">' +
      "Validation and backtest" +
      "</summary><div class=\"bt-details-body\">" +
      validationPanel() + modelPanel(d.model || {}) + "</div></details>");
    return out.join("");
  }

  // One sentence above the toggle, so the topline is never behind a click. It
  // reads the same validation state the panel does, so the two cannot drift.
  function trustTopline() {
    var v = vstate();
    var m = (S.data && S.data.pick_meta) || {};
    var vin = (v || {}).vintage || {};
    var need = vin.min_graded_games_for_min_edge;
    var have = vin.n_graded;
    if (v && v.validated) {
      return note("Validated: the vintage mode cleared every gate. The " + selNounPl() +
        " above clear " + floorText(m) + ".");
    }
    var s = "<strong>Not validated.</strong> ";
    if (need != null) {
      s += "The vintage backtest has graded " + (have == null ? "-" : have) +
        " of the " + need + " games needed to measure an edge threshold, so the " +
        selNounPl() + " above clear " + floorText(m) + ".";
    } else {
      s += "No minimum edge is measured, so the " + selNounPl() +
        " above clear a policy floor.";
    }
    return note(s);
  }

  // ===========================================================================
  // INLINE SVG CHARTS (A6, 2026-08-16). No chart library: every mark is a
  // hand-written SVG element, every colour is a theme token via a CSS class
  // (the same dialect the .bt-bar histogram set), lines are 2px, dots are 8px
  // across, grid and references are recessive, and text wears text tokens.
  // Native <title> elements give every data mark a browser tooltip with no
  // event wiring. Every chart has an absence branch that names WHY it is not
  // drawable, because a blank plot reads as a broken page.
  // ===========================================================================
  function chartAbsent(title, why) {
    return pxState("unmeasured", "<strong>" + esc(title) +
      ": not measured yet.</strong> " + esc(why));
  }

  // The reliability curve: predicted vs actual per decile, the diagonal as
  // the reference, one dot per non-empty bin. Bin n rides in each dot's
  // tooltip AND as a fine-print row, and the full table stays right below,
  // so the picture never replaces the numbers.
  function reliabilitySVG(bins, label) {
    var pts = [];
    (bins || []).forEach(function (b) {
      if (b && b.pred != null && b.actual != null) pts.push(b);
    });
    if (!pts.length) {
      return chartAbsent("Reliability curve",
        "every calibration bin is empty; bins fill as sides settle.");
    }
    var W = 320, H = 240, L = 34, B = 22, T = 8, R = 10;
    var pw = W - L - R, ph = H - T - B;
    function X(v) { return L + v * pw; }
    function Y(v) { return T + (1 - v) * ph; }
    var s = ['<svg class="bt-svg bt-svg-rel" viewBox="0 0 ' + W + " " + H +
             '" role="img" aria-label="' +
             esc("Reliability curve" + (label ? ", " + label : "")) + '">'];
    [0, 0.5, 1].forEach(function (v) {
      s.push('<line class="bt-svg-grid" x1="' + X(0) + '" y1="' + Y(v) +
             '" x2="' + X(1) + '" y2="' + Y(v) + '"/>');
      s.push('<line class="bt-svg-grid" x1="' + X(v) + '" y1="' + Y(0) +
             '" x2="' + X(v) + '" y2="' + Y(1) + '"/>');
      s.push('<text class="bt-svg-axis" x="' + (L - 4) + '" y="' + (Y(v) + 3) +
             '" text-anchor="end">' + v + "</text>");
      s.push('<text class="bt-svg-axis" x="' + X(v) + '" y="' + (H - 8) +
             '" text-anchor="middle">' + v + "</text>");
    });
    s.push('<line class="bt-svg-ref" x1="' + X(0) + '" y1="' + Y(0) +
           '" x2="' + X(1) + '" y2="' + Y(1) + '"><title>perfect calibration: ' +
           "predicted equals actual</title></line>");
    var path = pts.map(function (b, i) {
      return (i ? "L" : "M") + X(b.pred).toFixed(1) + " " + Y(b.actual).toFixed(1);
    }).join(" ");
    if (pts.length > 1) s.push('<path class="bt-svg-line" d="' + path + '"/>');
    pts.forEach(function (b) {
      s.push('<circle class="bt-svg-dot" r="4" cx="' + X(b.pred).toFixed(1) +
             '" cy="' + Y(b.actual).toFixed(1) + '"><title>' +
             esc("bin " + b.bin + ": n " + b.n + ", predicted " + num(b.pred, 3) +
                 ", actual " + num(b.actual, 3)) + "</title></circle>");
    });
    s.push('<text class="bt-svg-axis" x="' + (L + pw / 2) + '" y="' + (H - 0.5) +
           '" text-anchor="middle">predicted</text>');
    s.push('<text class="bt-svg-axis" transform="rotate(-90 9 ' + (T + ph / 2) +
           ')" x="9" y="' + (T + ph / 2) + '" text-anchor="middle">actual</text>');
    s.push("</svg>");
    var ns = (bins || []).map(function (b) { return b ? (b.n || 0) : 0; }).join(", ");
    return '<div class="bt-chart">' + s.join("") +
      '<div class="bt-clock-fine">Above the diagonal: resolved more often than ' +
      "predicted. Bin n, low bin to high: " + esc(ns) + ".</div></div>";
  }

  // The per-market branch exists so the day the learning artifact grows
  // per-market bins the curves appear with no client change; today it does
  // not carry them and the pooled curve says so out loud.
  function reliabilityBlock(L) {
    var cal = (L || {}).calibration || null;
    if (!cal) {
      return chartAbsent("Reliability curve", auxMissing("learning"));
    }
    var bym = (L || {}).by_market || {};
    var withBins = Object.keys(bym).filter(function (k) {
      return ((bym[k] || {}).bins || []).length;
    });
    if (withBins.length) {
      return withBins.map(function (k) {
        return '<div class="bt-panel-sub">' + esc(k) + "</div>" +
          reliabilitySVG(bym[k].bins, k);
      }).join("");
    }
    return reliabilitySVG(cal.bins, "pooled") +
      note("Pooled across markets: data/betting_learning.json carries " +
        "per-market summaries without per-market bins.");
  }

  // The Brier trend against the 0.25 coin line, from the learning history.
  // Rendered here for the first time anywhere: the history rows have carried
  // calibration_brier since the artifact existed and nothing plotted them.
  function brierTrendSVG(history) {
    var pts = [];
    (history || []).forEach(function (h) {
      if (h && h.calibration_brier != null) {
        pts.push({ date: h.date || "", v: Number(h.calibration_brier),
                   n: h.calibration_n_settled });
      }
    });
    if (pts.length < 2) {
      return chartAbsent("Brier trend",
        pts.length + " usable nightly row(s) in the learning history; a trend needs 2.");
    }
    var W = 320, H = 150, L = 40, B = 20, T = 8, R = 10;
    var pw = W - L - R, ph = H - T - B;
    var vals = pts.map(function (p) { return p.v; }).concat([0.25]);
    var lo = Math.min.apply(null, vals), hi = Math.max.apply(null, vals);
    var pad = Math.max(0.005, (hi - lo) * 0.15);
    lo -= pad; hi += pad;
    function X(i) { return L + (pts.length === 1 ? 0 : (i / (pts.length - 1)) * pw); }
    function Y(v) { return T + (1 - (v - lo) / (hi - lo)) * ph; }
    var s = ['<svg class="bt-svg bt-svg-trend" viewBox="0 0 ' + W + " " + H +
             '" role="img" aria-label="calibration Brier by night against the ' +
             '0.25 coin line">'];
    s.push('<line class="bt-svg-goldref" x1="' + L + '" y1="' + Y(0.25) +
           '" x2="' + (W - R) + '" y2="' + Y(0.25) +
           '"><title>0.25: a coin scores this</title></line>');
    s.push('<text class="bt-svg-axis" x="' + (W - R) + '" y="' + (Y(0.25) - 3) +
           '" text-anchor="end">coin 0.25</text>');
    var path = pts.map(function (p, i) {
      return (i ? "L" : "M") + X(i).toFixed(1) + " " + Y(p.v).toFixed(1);
    }).join(" ");
    s.push('<path class="bt-svg-line" d="' + path + '"/>');
    pts.forEach(function (p, i) {
      s.push('<circle class="bt-svg-dot" r="4" cx="' + X(i).toFixed(1) +
             '" cy="' + Y(p.v).toFixed(1) + '"><title>' +
             esc(p.date + ": Brier " + num(p.v, 5) +
                 (p.n != null ? " on " + p.n + " settled sides" : "")) +
             "</title></circle>");
    });
    s.push('<text class="bt-svg-axis" x="' + (L - 4) + '" y="' + (Y(hi - 0) + 3) +
           '" text-anchor="end">' + num(hi, 3) + "</text>");
    s.push('<text class="bt-svg-axis" x="' + (L - 4) + '" y="' + (Y(lo) + 3) +
           '" text-anchor="end">' + num(lo, 3) + "</text>");
    s.push('<text class="bt-svg-axis" x="' + L + '" y="' + (H - 6) + '">' +
           esc(pts[0].date) + "</text>");
    s.push('<text class="bt-svg-axis" x="' + (W - R) + '" y="' + (H - 6) +
           '" text-anchor="end">' + esc(pts[pts.length - 1].date) + "</text>");
    s.push("</svg>");
    return '<div class="bt-chart">' + s.join("") +
      '<div class="bt-clock-fine">Every priced side, scored on the binary outcome. ' +
      "Below the gold line beats a coin.</div></div>";
  }

  function brierTrendBlock() {
    var art = aux("learning");
    if (!art) {
      return chartAbsent("Brier trend", auxMissing("learning"));
    }
    return brierTrendSVG(art.history);
  }

  // One SVG progress bar, the shared mark for the three clocks. The track
  // and fill are 14px tall with the percentage as text beside them, so the
  // bar never has to be read by eye alone.
  function svgProgress(have, need, cls) {
    if (have == null || !need) return "";
    var f = Math.max(0, Math.min(1, Number(have) / Number(need)));
    var W = 220, H = 14;
    return '<svg class="bt-svg bt-svg-meter" viewBox="0 0 ' + (W + 54) + " " + H +
      '" role="img" aria-label="' + esc(have + " of " + need) + '">' +
      '<rect class="bt-svg-track" x="0.5" y="0.5" width="' + (W - 1) +
      '" height="' + (H - 1) + '"/>' +
      '<rect class="' + (cls || "bt-svg-fill") + '" x="1" y="1" width="' +
      Math.max(0, (W - 2) * f).toFixed(1) + '" height="' + (H - 2) +
      '"><title>' + esc(have + " of " + need) + "</title></rect>" +
      '<text class="bt-svg-axis" x="' + (W + 6) + '" y="' + (H - 3) + '">' +
      esc(pct(f, 1)) + "</text></svg>";
  }
  // Everything here used to be buried under a <details> on the pick tab or
  // absent entirely. It is the trust surface, so it gets its own tab and it
  // LEADS with the result rather than with the method.
  //
  // THE TWO CLOCKS ARE NEVER MERGED. One counts games the model was graded on
  // out of sample; the other counts settled paper bets, per selection rule.
  // They measure different things, they open different gates, and adding them
  // is exactly the arithmetic that produced the "600 bets" question: nobody is
  // waiting on 600 bets, and nobody is waiting on 100 games.

  function vintageBlock(v) {
    var bs = ((v || {}).graded_blocks) || [];
    for (var i = 0; i < bs.length; i++) {
      if (bs[i].key === "vintage" || bs[i].mode === "vintage") return bs[i];
    }
    return null;
  }

  // THE RESULT, UNSOFTENED. The verb comes from the sign of the served paired
  // delta and from `beats_baseline_95`, so it can never flatter a number the
  // artifact did not report. There is no adjective in this function.
  function honestResult() {
    var v = vstate();
    var b = vintageBlock(v);
    var n = b ? ((b.n_graded != null) ? b.n_graded : b.n) : null;
    if (!b || !n) {
      return '<div class="bt-headline bt-headline-warn">' +
        '<div class="bt-headline-hd">The vintage backtest has graded nothing yet</div>' +
        "<p>" + gl("Vintage mode", "vintage_grading") + " is the only out-of-sample " +
        "mode: " + (b && b.status ? esc(b.status) : "no graded games") + ". Every " +
        "Brier on this page comes from a contaminated mode whose features contain " +
        "the games it grades.</p></div>";
    }
    var sk = b.skill_vs_home_base || {};
    var d = sk.delta;
    var verb = (d == null) ? "has no measured margin against"
      : (d < 0 ? "LOSES to"
              : (sk.beats_baseline_95 ? "beats" : "does not significantly beat"));
    // The bar is read off the served gate's own need string; no number is
    // typed here, so a bar that moves server-side moves this chip with it.
    var bar = gateNeedValue(gateById(v, "out_of_sample_skill"), v).n;
    var lad = ladderPosition();
    var homeLine = "The vintage backtest " + verb + " &quot;always take the home team&quot;";
    return '<div class="bt-headline bt-headline-warn">' +
      '<div class="bt-headline-hd">' + (lad ? lad.head : homeLine) + "</div>" +
      '<div class="bt-pick-nums">' +
      chip("Games", n) + chip("Brier", num(b.brier, 5)) +
      chip("Home base", num(b.brier_home_base, 5)) +
      chip("Accuracy", pct(b.accuracy, 2)) +
      chip("Skill", signed(d, 6)) + chip("t", num(sk.t, 3)) +
      (bar == null ? "" : chip("t bar", num(bar, 3))) + "</div>" +
      (lad ? "<p>" + homeLine + "." + lad.market + "</p>" : "") +
      "<p>Out of sample, paired per game. Lower " + gl("Brier", "brier_score") +
      " is better. This gate decides whether anything is published as a " +
      selNoun() + ".</p>" + pricerLine() + "</div>";
  }

  // THE HEADLINE LEADS WITH THE LADDER (M12-09, 2026-09-25). It used to lead
  // with the one baseline the model beats, always-home, while the benchmark
  // panel further down the same tab ranks a zero-parameter literature Elo
  // above the model on the same games and the de-vigged market open above
  // every tier on the games it covers. The position is read off the eval
  // artifact's own benchmarks block, sorted by measured Brier over the
  // full-window tiers exactly as benchmarkPanel sorts them, so no rank or
  // number here is typed.
  var TIER_NAMES = {
    model_vintage: "the model", elo_literature: "a literature Elo",
    home_constant: "always home", market_open_devig: "the de-vigged market open",
    market_close_devig: "the de-vigged market close"
  };
  function tierName(k) { return TIER_NAMES[k] || String(k).replace(/_/g, " "); }
  function ladderPosition() {
    var bm = (aux("evald") || {}).benchmarks;
    if (!bm || !bm.tiers || !bm.tiers.model_vintage) return null;
    var w = bm.window || {};
    var full = [], sub = [];
    Object.keys(bm.tiers).forEach(function (k) {
      var t = bm.tiers[k] || {};
      if (!t.n || t.brier == null) return;
      if (w.n != null && t.n < w.n) sub.push({ key: k, t: t });
      else full.push({ key: k, brier: t.brier });
    });
    full.sort(function (a, c) { return a.brier - c.brier; });
    var pos = -1;
    full.forEach(function (r, i) { if (r.key === "model_vintage") pos = i; });
    if (pos < 0) return null;
    var ahead = full.slice(0, pos).map(function (r) { return tierName(r.key); });
    var head = "Vintage backtest" + (w.n != null ? " on " + w.n + " games" : "") +
      ": the model ranks " + (pos + 1) + " of " + full.length + " measured tiers" +
      (ahead.length ? ", behind " + esc(ahead.join(" and ")) : "");
    // A subsample tier never ranks in the headline (the artifact's claim
    // rule); it is compared only inside its own same-games block.
    var market = sub.map(function (r) {
      var sg = r.t.same_games || {};
      if (sg.model == null) return "";
      var better = r.t.brier < sg.model;
      return " On the " + r.t.n + " of " + (w.n == null ? "-" : w.n) + " games it covers, " +
        esc(tierName(r.key)) + " scores " + num(r.t.brier, 5) + " against the model's " +
        num(sg.model, 5) + (better ? ", better than the model." : ".");
    }).join("");
    return { head: head, market: market };
  }

  // WHICH PRICER THE BACKTEST GRADES (M12-09, 2026-09-25). The vintage grade
  // is of coefficients fitted once on the fit window and scored forward; the
  // board serves a season-to-date fit. Both coefficient sets are served (the
  // eval artifact's vintage block, fetched as evald, and the payload's model
  // block), so the line
  // prints both offense slopes rather than letting one Brier stand for both.
  function pricerLine() {
    var ev = (aux("evald") || {}).vintage || {};
    var gc = ev.coefficients || null;
    var sc = (S.data && S.data.model && S.data.model.coefficients) || null;
    var fw = ev.fit_window || {};
    if (!gc || !sc || gc.b1 == null || sc.b1 == null) return "";
    return "<p>The graded pricer's coefficients were fitted once on " +
      (gc.n_rows == null ? "its fit window" : gc.n_rows + " team-game rows") +
      (fw.first_date ? " (" + esc(fw.first_date) + " to " + esc(fw.last_date || "-") + ")" : "") +
      " and scored forward; the board serves a season-to-date fit on " +
      (sc.n_rows == null ? "every row to date" : sc.n_rows + " rows") +
      ". Runs per sigma of offense: " + num(gc.b1, 3) + " graded, " + num(sc.b1, 3) +
      " served. This result grades that method, not the exact pricer on the board; " +
      "a grade of the served pricer is pre-registered and has not run.</p>";
  }

  function clockA() {
    var L = ((aux("learning") || {}).latest) || {};
    var c = (L.clocks || {}).vintage_sample || null;
    var v = vstate();
    var vin = (v || {}).vintage || {};
    var have = c ? c.have : vin.n_graded;
    var need = c ? c.need : vin.min_graded_games_for_min_edge;
    var rate = (c || {}).rate || null;
    var eta = (c || {}).eta || null;
    var rows = ['<div class="bt-clock-hd">Clock A &middot; vintage-graded games</div>',
      '<div class="bt-clock-q">Games priced only from snapshots dated before them.</div>',
      '<div class="bt-clock-n">' + (have == null ? "-" : have) +
        ' <span class="bt-clock-need">of ' + (need == null ? "-" : need) + "</span></div>",
      meter(have, need)];
    rows.push('<div class="bt-kv">' +
      kv("Measured arrivals per day", rate ? num(rate.per_day, 2) : "not measured") +
      kv("Counted over", rate ? (rate.window_days + " days from " + esc(rate.window_from))
                              : "-") +
      kv("Short by", (have != null && need != null) ? (need - have) + " games" : "-") +
      kv("Days at that rate", eta && eta.days != null ? eta.days : "not projected") +
      "</div>");
    if (eta && eta.is_projection) {
      rows.push(note("Projection: the measured rate applied forward. " +
        esc(rate ? rate.basis : "")));
    }
    if (c && c.may_go_backwards) {
      rows.push('<div class="bt-clock-fine">May go backwards: ' + esc(c.may_go_backwards) +
        "</div>");
    }
    if (!c) rows.push(note(esc(auxMissing("learning")) +
      " The count is from the payload; no arrival rate."));
    return '<div class="bt-clock">' + rows.join("") + "</div>";
  }

  function clockB() {
    var L = ((aux("learning") || {}).latest) || {};
    var c = (L.clocks || {}).graded_price_history || null;
    var rows = ['<div class="bt-clock-hd">Clock B &middot; settled paper bets, per tag</div>',
      '<div class="bt-clock-q">Per selection rule: does any edge threshold clear an ' +
      "ROI lower bound of 0?</div>"];
    if (!c) {
      rows.push(note(esc(auxMissing("learning"))));
      return '<div class="bt-clock">' + rows.join("") + "</div>";
    }
    var tags = c.by_tag || {};
    var keys = Object.keys(tags).sort();
    rows.push('<div class="bt-scroll mlbstats-scroll"><table class="bt-table mlbstats-table">' +
      '<thead><tr><th class="bt-l">Tag</th><th>Settled</th><th>Need</th>' +
      '<th class="bt-l">Progress</th>' +
      "<th>Per day</th><th>Days at that rate</th><th>State</th></tr></thead><tbody>" +
      keys.map(function (k) {
        var t = tags[k] || {};
        var r = t.rate || {}, e = t.eta || {};
        var need = (t.need == null ? c.need_per_tag : t.need);
        return '<tr><td class="bt-l">' + esc(k) + "</td><td>" +
          (t.have == null ? "-" : t.have) + "</td><td>" +
          (need == null ? "-" : need) +
          '</td><td class="bt-l bt-cell-meter">' +
          (svgProgress(t.have, need) || '<span class="bt-dim">-</span>') +
          "</td><td>" + num(r.per_day, 3) + "</td><td>" +
          (e.days == null ? "-" : e.days) + "</td><td>" +
          '<span class="bt-tag ' + (t.ready ? "bt-tag-ok" : "bt-tag-warn") + '">' +
          (t.ready ? "ready" : "short") + "</span></td></tr>";
      }).join("") + "</tbody></table></div>");
    rows.push(note(esc(c.why_per_tag || "")));
    if (c.cost) rows.push('<div class="bt-clock-fine">' + esc(c.cost) + "</div>");
    return '<div class="bt-clock">' + rows.join("") + "</div>";
  }

  // The clock meter, an SVG progress bar since A6 (2026-08-16). Clamped at
  // 100 so an overshoot cannot render past its own box; the percentage rides
  // as text beside the bar so nothing is read by eye alone.
  function meter(have, need) {
    var bar = svgProgress(have, need);
    if (!bar) return "";
    var f = Math.max(0, Math.min(1, Number(have) / Number(need)));
    return '<div class="bt-meter">' + bar + "</div>" +
      '<div class="bt-clock-fine">' + pct(f, 1) + " of target</div>";
  }

  // Clock C: the GRADABLE pool behind Clock A. Not a third gate: it counts
  // completed games a dated snapshot can price at all, which is the ceiling
  // on what Clock A can ever grade. The learning artifact carries no clock
  // for it, so the rate and ETA say so instead of being invented.
  function clockGradable() {
    var L = ((aux("learning") || {}).latest) || {};
    var c = (L.clocks || {}).gradable_games || null;
    var vs = (L.clocks || {}).vintage_sample || null;
    var v = vstate();
    var vin = (v || {}).vintage || {};
    // A fallback CHAIN, not a pick: the learning artifact's own clock first,
    // its vintage_sample block second, the payload's vintage block last, so a
    // count that exists anywhere served still draws.
    var have = c && c.have != null ? c.have : null;
    if (have == null && vs && vs.n_gradable != null) have = vs.n_gradable;
    if (have == null && vin.n_gradable != null) have = vin.n_gradable;
    var need = c && c.need != null ? c.need : null;
    if (need == null && vs && vs.need != null) need = vs.need;
    if (need == null && vin.min_graded_games_for_min_edge != null) {
      need = vin.min_graded_games_for_min_edge;
    }
    var rows = ['<div class="bt-clock-hd">Clock C &middot; gradable games (the pool)</div>',
      '<div class="bt-clock-q">Completed games a dated snapshot covers; the ceiling ' +
      "on Clock A.</div>"];
    if (have == null) {
      rows.push(chartAbsent("Gradable pool",
        "neither the learning artifact nor the payload reports n_gradable."));
      return '<div class="bt-clock">' + rows.join("") + "</div>";
    }
    rows.push('<div class="bt-clock-n">' + have +
      ' <span class="bt-clock-need">of ' + (need == null ? "-" : need) + "</span></div>");
    rows.push(meter(have, need));
    var rate = (c || {}).rate || null;
    var eta = (c || {}).eta || null;
    rows.push('<div class="bt-kv">' +
      kv("Measured arrivals per day", rate ? num(rate.per_day, 2)
        : "not measured: the learning artifact carries no gradable_games clock") +
      kv("Days at that rate", eta && eta.days != null ? eta.days : "not projected") +
      "</div>");
    rows.push('<div class="bt-clock-fine">Not a gate. A pool below the Clock A bar ' +
      "caps the graded count.</div>");
    return '<div class="bt-clock">' + rows.join("") + "</div>";
  }

  function clocksPanel() {
    return '<div class="bt-panel"><div class="bt-panel-hd">Two clocks and the pool</div>' +
      "<p>Clock A counts games graded out of sample; Clock B counts settled paper " +
      "bets per selection rule. They open different " + gl("gates", "validation_clocks") +
      " and may never be added together. Clock C is the gradable pool that caps " +
      "Clock A.</p>" +
      '<div class="bt-clocks">' + clockA() + clockB() + clockGradable() + "</div></div>";
  }

  function calibrationPanel() {
    var L = ((aux("learning") || {}).latest) || {};
    var cal = L.calibration || null;
    var rows = ['<div class="bt-panel-hd">Calibration ledger</div>'];
    if (!cal) {
      return '<div class="bt-panel">' + rows.join("") + "<p>" +
        esc(auxMissing("learning")) + "</p></div>";
    }
    rows.push('<div class="bt-kv">' +
      kv("Rows", cal.n_rows == null ? "-" : cal.n_rows) +
      kv("Settled", cal.n_settled == null ? "-" : cal.n_settled) +
      kv("Open", cal.n_open == null ? "-" : cal.n_open) +
      kv("Slate days", cal.n_slate_days == null ? "-" : cal.n_slate_days) +
      kv("Brier", num(cal.brier, 6)) +
      kv("Log loss", num(cal.log_loss, 6)) + "</div>");
    // A6 (2026-08-16): the picture beside the numbers, never instead of them.
    rows.push('<div class="bt-panel-sub">' + gl("Reliability curve", "reliability_curve") +
      "</div>");
    rows.push(reliabilityBlock(L));
    rows.push('<div class="bt-panel-sub">Brier by night, against the coin</div>');
    rows.push(brierTrendBlock());
    rows.push('<div class="bt-scroll mlbstats-scroll"><table class="bt-table mlbstats-table">' +
      '<thead><tr><th class="bt-l">Bin</th><th>n</th><th>Predicted</th><th>Actual</th>' +
      "<th>|pred - actual|</th></tr></thead><tbody>" +
      (cal.bins || []).map(function (b) {
        var gap = (b.pred == null || b.actual == null) ? null
          : Math.abs(Number(b.pred) - Number(b.actual));
        return '<tr><td class="bt-l">' + esc(b.bin) + "</td><td>" + (b.n || 0) +
          "</td><td>" + num(b.pred, 4) + "</td><td>" + num(b.actual, 4) + "</td>" +
          '<td class="' + (gap != null && gap >= 0.2 ? "bt-neg" : "") + '">' +
          num(gap, 4) + "</td></tr>";
      }).join("") + "</tbody></table></div>");
    if (cal.not_gate_1) rows.push(note(esc(cal.not_gate_1)));

    var bym = L.by_market || null;
    if (bym) {
      rows.push('<div class="bt-panel-sub">Per market</div>');
      var mk = Object.keys(bym);
      rows.push('<div class="bt-scroll mlbstats-scroll"><table class="bt-table mlbstats-table">' +
        '<thead><tr><th class="bt-l">Market</th><th>Rows</th><th>Settled</th><th>Brier</th>' +
        "<th>Log loss</th><th>Hold %</th><th>Model p</th><th>Market fair p</th>" +
        "<th>Hit rate</th><th>Bias</th></tr></thead><tbody>" +
        mk.map(function (k) {
          var m = bym[k] || {}, cs = m.canonical_side || {};
          return '<tr><td class="bt-l">' + esc(k) + "</td><td>" +
            (m.n_rows == null ? "-" : m.n_rows) + "</td><td>" +
            (m.n_settled == null ? "-" : m.n_settled) + "</td><td>" +
            num(m.brier, 6) + "</td><td>" + num(m.log_loss, 6) + "</td><td>" +
            num(m.mean_hold_pct, 3) + "</td><td>" + num(cs.mean_model_prob, 4) +
            "</td><td>" + num(cs.mean_market_fair_prob, 4) + "</td><td>" +
            num(cs.hit_rate, 4) + "</td><td>" + num(cs.bias, 4) + "</td></tr>";
        }).join("") + "</tbody></table></div>");
      var any = mk.length ? (bym[mk[0]] || {}).canonical_side : null;
      if (any && any.note) rows.push(note(esc(any.note) +
        " A Poisson margin underweights the tails, so a shape error shows first on the " +
        "runline and total. n = " + (any.n == null ? "-" : any.n) +
        " canonical rows per market: too few to conclude from."));
    }
    return '<div class="bt-panel">' + rows.join("") + "</div>";
  }

  // THE BENCHMARK LADDER (A6, 2026-08-16), read off the eval artifact's
  // benchmarks block. Sorted by measured Brier, best first, over the tiers
  // graded on the FULL window, so the order is data, not authorship; on the
  // current artifact the model sits LAST and the panel says so rather than
  // burying it. The subsample tier renders apart with its same_games block
  // (the only comparison a subsample may appear in) and an unmeasured tier
  // renders its own status sentence instead of a number it does not have.
  function benchmarkPanel() {
    var e = aux("evald") || {};
    var b = e.benchmarks || null;
    var rows = ['<div class="bt-panel-hd">' + gl("Benchmark ladder", "benchmark_ladder") +
      "</div>"];
    if (!b || !b.tiers) {
      rows.push(chartAbsent("Benchmark ladder",
        (auxState("evald") === "ok"
          ? "data/betting_model_eval.json carries no benchmarks block."
          : auxMissing("evald"))));
      return '<div class="bt-panel">' + rows.join("") + "</div>";
    }
    var w = b.window || {};
    var full = [], sub = [], unmeasured = [];
    Object.keys(b.tiers).forEach(function (k) {
      var t = b.tiers[k] || {};
      var row = { key: k, n: t.n, brier: t.brier, t: t };
      if (!t.n || t.brier == null) unmeasured.push(row);
      else if (w.n != null && t.n < w.n) sub.push(row);
      else full.push(row);
    });
    full.sort(function (a, c) { return a.brier - c.brier; });
    var modelLast = full.length && full[full.length - 1].key === "model_vintage";
    rows.push("<p>Every tier scored on the same " + (w.n == null ? "-" : w.n) +
      "-game vintage eval window, " + esc(w.first_date || "-") + " to " +
      esc(w.last_date || "-") + ". Lower Brier is better." +
      (modelLast ? " <strong>The model is last on this window.</strong>" : "") + "</p>");
    rows.push('<div class="bt-scroll mlbstats-scroll"><table class="bt-table mlbstats-table">' +
      '<thead><tr><th class="bt-l">Tier</th><th>Games</th><th>Brier</th>' +
      '<th class="bt-l">Basis</th></tr></thead><tbody>' +
      full.map(function (r) {
        var isModel = r.key === "model_vintage";
        return '<tr' + (isModel ? ' class="bt-bestrow"' : "") + '><td class="bt-l">' +
          esc(r.key) + (isModel ? ' <span class="bt-tag bt-tag-warn">the model</span>' : "") +
          "</td><td>" + r.n + "</td><td>" + num(r.brier, 5) +
          '</td><td class="bt-l bt-gate-need">' + esc(r.t.source || "") + "</td></tr>";
      }).join("") + "</tbody></table></div>");
    sub.forEach(function (r) {
      var sg = r.t.same_games || {};
      rows.push('<div class="bt-panel-sub">' + esc(r.key) + ", a subsample (" +
        r.n + " of " + (w.n == null ? "-" : w.n) + " games)</div>");
      rows.push("<p>" + esc(r.t.subsample_note || "") + " Compare its Brier (" +
        num(r.brier, 5) + ") only inside its same-games block: model " +
        num(sg.model, 5) + ", home constant " + num(sg.home_constant, 5) +
        ", elo " + num(sg.elo_literature, 5) + ".</p>");
    });
    unmeasured.forEach(function (r) {
      rows.push(chartAbsent(r.key, r.t.status || "n = 0, no number."));
    });
    if (b.claim_rule) rows.push(note(esc(b.claim_rule)));
    return '<div class="bt-panel">' + rows.join("") + "</div>";
  }

  // The gate returned INDETERMINATE and it is rendered as INDETERMINATE.
  // `verdict` GOVERNS: `passed` is one pre-registered split, the sweep is the
  // ship decision, and the two genuinely disagree right now. Rendering the
  // boolean would publish a pass the module refused to serve.
  function dispersionPanel() {
    var e = aux("evald") || {};
    var dr = e.run_dispersion || null;
    var rows = ['<div class="bt-panel-hd">' + gl("Run dispersion", "run_dispersion") +
      ": the margin model gate</div>"];
    if (!dr) {
      var L = ((AUX.learning || {}).latest) || {};
      var d2 = L.dispersion || null;
      rows.push("<p>" + esc(auxMissing("evald")) + "</p>");
      if (d2) {
        rows.push('<div class="bt-kv">' + kv("Status", esc(d2.status || "-")) +
          kv("Alpha", num(d2.alpha, 5)) +
          kv("Served", d2.served ? "yes" : "no") + "</div>");
        rows.push(note("From data/betting_learning.json: the single split only, NOT the " +
          "split-quantile sweep the verdict is taken from."));
      }
      return '<div class="bt-panel">' + rows.join("") + "</div>";
    }
    var sens = dr.sensitivity || {};
    var verdict = String(dr.verdict || sens.verdict || "unknown");
    var cls = verdict === "pass" ? "bt-tag-ok" : "bt-tag-warn";
    // The gloss is keyed to the verdict it glosses. Unconditional, it would
    // have called a served pass or a clean fail "not a pass and not a failure".
    rows.push("<p><strong>Verdict: " +
      '<span class="bt-tag ' + cls + '">' + esc(verdict) + "</span></strong> " +
      (verdict === "indeterminate" ? "Not a pass and not a failure. " : "") +
      esc(dr.verdict_note || "") + "</p>");
    rows.push('<div class="bt-kv">' +
      kv("Fitted alpha (NB2)", num(dr.alpha, 5)) +
      kv("Variance ratio", varianceRatioText(dr)) +
      kv("Single pre-registered split", dr.passed ? "all four criteria pass" :
                                                    "at least one criterion fails") +
      kv("Served in prices", dr.served ? "yes" : "no") +
      kv("Served alpha", dr.served_alpha == null ? "none, prices stay Poisson"
                                                 : num(dr.served_alpha, 5)) +
      kv("Held-out games", dr.n_eval_games == null ? "-" : dr.n_eval_games) + "</div>");

    var grid = sens.grid || [];
    if (grid.length) {
      rows.push('<div class="bt-panel-sub">Criterion 2 by split point and by side</div>');
      rows.push('<div class="bt-scroll mlbstats-scroll"><table class="bt-table mlbstats-table">' +
        '<thead><tr><th class="bt-l">Split q</th><th>Date</th><th>Eval games</th>' +
        "<th>Home delta</th><th>Home t</th><th>Away delta</th><th>Away t</th>" +
        "<th>Both delta</th><th>Both t</th><th>Gate</th></tr></thead><tbody>" +
        grid.map(function (g) {
          var bs = g.by_side || {}, h = bs.home || {}, a = bs.away || {}, b = bs.both || {};
          var pass = (g.gate_by_side || {}).both;
          return '<tr><td class="bt-l">' + num(g.split_q, 2) + "</td><td>" +
            esc(g.split_date || "-") + "</td><td>" + (g.n_eval_games == null ? "-" : g.n_eval_games) +
            '</td><td class="' + (h.delta < 0 ? "bt-neg" : "bt-pos") + '">' + signed(h.delta, 6) +
            "</td><td>" + num(h.t, 3) +
            '</td><td class="' + (a.delta < 0 ? "bt-neg" : "bt-pos") + '">' + signed(a.delta, 6) +
            "</td><td>" + num(a.t, 3) +
            '</td><td class="' + (b.delta < 0 ? "bt-neg" : "bt-pos") + '">' + signed(b.delta, 6) +
            "</td><td>" + num(b.t, 3) + "</td><td>" +
            '<span class="bt-tag ' + (pass ? "bt-tag-ok" : "bt-tag-warn") + '">' +
            (pass ? "pass" : "fail") + "</span></td></tr>";
        }).join("") + "</tbody></table></div>");
      if (sens.rule) rows.push(note(esc(sens.rule)));
    }
    if (dr.runline_side_note) {
      rows.push('<div class="bt-clock-fine">' + esc(dr.runline_side_note) + "</div>");
    }
    if (dr.criteria) {
      rows.push('<details class="bt-details"><summary class="bt-details-sum">' +
        "The pre-registered criteria, as amended</summary>" +
        '<div class="bt-details-body"><p>' + esc(dr.criteria) + "</p>" +
        (dr.criteria_v1 ? "<p><strong>V1, superseded:</strong> " + esc(dr.criteria_v1) +
          "</p>" : "") + "</div></details>");
    }
    return '<div class="bt-panel">' + rows.join("") + "</div>";
  }

  // The measured variance ratio is NOT in any served artifact: betting_model
  // measures it at fit time (its own header carries 2.3748x on the margin) and
  // publishes alpha alone. Deriving 1 + alpha*lambda here would be this page
  // inventing a number, so it says which file would have to carry it instead.
  function varianceRatioText(dr) {
    var vr = (dr || {}).variance_ratio;
    if (vr == null) return "not published by data/betting_model_eval.json";
    if (typeof vr === "number") return num(vr, 4) + "x";
    // The shaped form: the margin ratio is the one that decides a runline, and
    // the per-side ratio is the mechanism behind it.
    return num(vr.margin_ratio, 4) + "x on the margin, " +
      num(vr.runs_var_over_mean, 4) + "x per scoring side";
  }

  // ---- Futures -------------------------------------------------------------
  // THE SEASON-LONG OUTRIGHT BOARD, MODEL SIDE ONLY. There is no market here:
  // no futures price has ever been captured by this platform, so there is no
  // edge column, no value flag and no expected return. The tab says which
  // capture is missing rather than estimating one.
  //
  // THE PRICE COLUMN IS NOT CALLED FAIR. "Fair" asserts zero expected value,
  // which requires the probability to be right, and the simulator behind these
  // numbers has no validated forward record. It is the price IMPLIED by the
  // model's own probability, labelled that way, and it is BLANK at the rails
  // because p = 0 and p = 1 are both live in the artifact and an infinity
  // rendered into a price cell looks like a number.
  var FUT = null;
  var FUT_ERR = "";
  // THE POSTSEASON BRACKET SIMULATOR (docs/betting-2026-10/BRACKET_SIM_GATE.md,
  // section 8). During the postseason the Pennant and World Series columns read
  // the simulator's payload, labelled implied, no market, with its as-of date;
  // Division, Playoffs, Bye, Proj W and Win band keep the season simulator and
  // its end-of-season stamp. The interval and price cells print a dash for
  // those rows: the recursion is exact, and no price is derived from these
  // numbers. A missing payload, or one that does not serve, leaves the board
  // exactly as it renders without it. Every sentence comes from the payload.
  var BR = null;

  function loadFutures() {
    if (FUT || FUT_ERR) { paintAll(); return; }
    var br = fetch("/data/bracket_sim.json", { cache: "no-cache" })
      .then(function (r) { return r.ok ? r.json() : null; })
      .catch(function () { return null; });
    fetch("/data/futures.json", { cache: "no-cache" })
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
      .then(function (d) { return br.then(function (b) { BR = b; FUT = d; paintAll(); }); })
      .catch(function () {
        FUT_ERR = "data/futures.json did not load.";
        paintAll();
      });
  }

  // {on: true, b, by} while the simulator serves this season's board;
  // {on: false, b} on a day it did not update; null otherwise.
  function bracketOverlay() {
    var b = BR;
    if (!b || !b.serve || !FUT || b.season !== FUT.season) return null;
    if (b.serve.on && b.clubs && b.clubs.length) {
      var by = {};
      b.clubs.forEach(function (c) { by[c.team] = c; });
      return { on: true, b: b, by: by };
    }
    return b.serve.not_updated_note ? { on: false, b: b } : null;
  }

  function brPct(v) {
    return (v === null || v === undefined) ? '<span class="bt-dim">-</span>' : (v * 100).toFixed(1) + "%";
  }

  // The stamp lines above the board while the simulator serves, or the
  // did-not-update sentence beneath the season stamp on a day it did not.
  function brStamp(ov) {
    if (!ov) return "";
    var s = ov.b.serve;
    if (!ov.on) return '<p class="bt-note"><strong>' + esc(s.not_updated_note) + "</strong></p>";
    return (s.division_columns_note ? '<p class="bt-note"><strong>' + esc(s.division_columns_note) + "</strong></p>" : "") +
      '<p class="bt-note"><strong>' + esc(s.line) + "</strong></p>";
  }

  // The four tail cells of a board row: Pennant, World Series, WS interval and
  // the implied price. A club outside the postseason reads 0 (gate 6.1).
  function brCells(ov, c) {
    var r = ov.by[c.team] || { pennant_pct: 0, ws_pct: 0 };
    var dash = '<span class="bt-dim">-</span>';
    return "<td>" + brPct(r.pennant_pct) + "</td>" + "<td>" + brPct(r.ws_pct) + "</td>" +
      "<td>" + dash + "</td>" + "<td>" + dash + "</td>";
  }

  function brSort(ov, clubs) {
    return clubs.map(function (c, i) { return { c: c, i: i }; }).sort(function (x, y) {
      var a = (ov.by[x.c.team] || {}).ws_pct || 0, b = (ov.by[y.c.team] || {}).ws_pct || 0;
      return (b - a) || (x.i - y.i);
    }).map(function (x) { return x.c; });
  }

  // The postseason table below the board: one row per postseason club.
  function brPanel(ov) {
    var b = ov.b, cols = b.columns || {}, rec = b.record || {};
    var rows = b.clubs.map(function (c) {
      return "<tr>" + '<td class="bt-l">' + esc(c.team) + "</td>" +
        "<td>" + esc(c.seed) + "</td>" +
        '<td class="bt-l">' + esc(c.series_now_text || "") + "</td>" +
        "<td>" + brPct(c.p_round_now) + "</td>" +
        "<td>" + brPct(c.reach_lcs_pct) + "</td>" +
        "<td>" + brPct(c.pennant_pct) + "</td>" +
        "<td>" + brPct(c.ws_pct) + "</td></tr>";
    }).join("");
    return '<div class="bt-panel" data-bt-bracket="1"><div class="bt-panel-hd">Postseason bracket (' +
      esc(b.label) + ", as of " + esc(b.serve.as_of) + ")</div>" +
      '<div class="bt-scroll mlbstats-scroll"><table class="bt-table mlbstats-table"><thead><tr>' +
      '<th class="bt-l">Club</th><th>Seed</th><th class="bt-l">Series now</th>' +
      "<th>" + esc(cols.p_round_now) + "</th><th>" + esc(cols.reach_lcs) + "</th>" +
      "<th>" + esc(cols.pennant) + "</th><th>" + esc(cols.ws) + "</th>" +
      "</tr></thead><tbody>" + rows + "</tbody></table></div>" +
      '<p class="bt-note">' + esc(b.method) + " " + esc(b.never) + "</p>" +
      '<p class="bt-note"><strong>Postseason simulator record: ' + esc(rec.n_days) + " day" +
      (rec.n_days === 1 ? "" : "s") + " logged, " + esc(rec.n_crash_days) + " crash day" +
      (rec.n_crash_days === 1 ? "" : "s") + ", " + esc(rec.n_series_decided) + " series decided, " +
      esc(rec.n_scored) + " scored.</strong> " + esc(rec.what_it_is) + "</p></div>";
  }

  function futPrice(v) {
    // A blank, not an infinity and not a zero. btSortValue already treats a
    // dash as null, and the row still sorts on the probability.
    if (v === null || v === undefined) return '<span class="bt-dim">.</span>';
    return (v > 0 ? "+" : "") + v;
  }

  function renderFutures() {
    if (FUT_ERR) return '<p class="bt-note">' + esc(FUT_ERR) + "</p>";
    if (!FUT) { loadFutures(); return '<p class="bt-note">Loading.</p>'; }
    if (!FUT.clubs || !FUT.clubs.length) {
      return '<p class="bt-note">' + esc(FUT.empty_reason || "No board.") + "</p>";
    }
    var nm = FUT.no_market;
    var ov = bracketOverlay(), on = !!(ov && ov.on);
    var rows = (on ? brSort(ov, FUT.clubs) : FUT.clubs).map(function (c) {
      function p3(v) { return (v === null || v === undefined) ? "" : (v * 100).toFixed(1) + "%"; }
      var mc = c.mcWs || {};
      return "<tr>" +
        '<td class="bt-l">' + esc(c.team) + "</td>" +
        "<td>" + esc(c.record || "") + "</td>" +
        "<td>" + (c.projWins === null ? "" : c.projWins.toFixed(1)) + "</td>" +
        "<td>" + esc(c.winTotalP10) + " to " + esc(c.winTotalP90) + "</td>" +
        "<td>" + p3(c.divisionPct) + "</td>" +
        "<td>" + p3(c.playoffPct) + "</td>" +
        "<td>" + p3(c.byePct) + "</td>" +
        (on ? brCells(ov, c) :
        "<td>" + p3(c.pennantPct) + "</td>" +
        "<td>" + p3(c.wsPct) + "</td>" +
        '<td>' + ((mc.lo95 === undefined || mc.lo95 === null) ? "" :
          (mc.lo95 * 100).toFixed(1) + " to " + (mc.hi95 * 100).toFixed(1)) + "</td>" +
        '<td>' + futPrice(c.impliedAmericanWS) + "</td>") +
        "</tr>";
    }).join("");

    // THE SIMULATOR NEVER SEES A POSTSEASON GAME: it plays the bracket from final
    // standings, so once the regular season is over these odds stop learning.
    // The exporter derives the line from the payload's build date and the
    // season's last regular-season date and leaves it null before then.
    return '<div class="bt-panel"><div class="bt-panel-hd">Futures</div>' +
      (on ? brStamp(ov) :
        (FUT.as_of_note ? '<p class="bt-note"><strong>' + esc(FUT.as_of_note) + "</strong></p>" : "") +
        brStamp(ov)) +
      '<p class="bt-note"><strong>There is no market on this board.</strong> ' +
      esc(nm.what_is_missing) + "</p>" +
      '<p class="bt-note">' + esc(nm.what_would_have_to_happen) + " " +
      esc(nm.and_then_still_not_an_edge) + "</p>" +
      '<div class="bt-scroll mlbstats-scroll"><table class="bt-table mlbstats-table"><thead><tr>' +
      '<th class="bt-l">Club</th><th>Record</th><th>Proj W</th><th>Win band</th>' +
      "<th>Division</th><th>Playoffs</th><th>Bye</th><th>" + (on ? esc(ov.b.columns.pennant) : "Pennant") + "</th>" +
      "<th>" + (on ? esc(ov.b.columns.ws) : "World Series") + "</th><th>WS interval</th><th>Model price (implied)</th>" +
      "</tr></thead><tbody>" + rows + "</tbody></table></div>" +
      '<p class="bt-note">' + esc(FUT.why_the_price_column_is_not_called_fair) + "</p>" +
      '<p class="bt-note">' + esc(FUT.what_the_intervals_are) + "</p>" +
      '<p class="bt-note">' + esc(FUT.win_total_basis) + "</p>" +
      // THE FORWARD RECORD, STATED AT ITS TRUE LENGTH. The paragraph above says
      // this simulator has no validated forward record, which will stay true
      // until one accrues, and one cannot accrue while every night overwrites
      // the last. The ledger records what was published each day so a completed
      // season can be scored against the numbers that were live through it. It
      // reports how many entries exist and how many are graded, and today the
      // second number is zero. Saying so is the point: a record that describes
      // itself as a result before anything resolves is worse than no record.
      (FUT.ledger ? '<p class="bt-note"><strong>Forward record: ' +
        esc(FUT.ledger.n_entries) + ' day' + (FUT.ledger.n_entries === 1 ? '' : 's') +
        ' logged, ' + esc(FUT.ledger.n_resolved) + ' scored.</strong> ' +
        esc(FUT.ledger.what_it_is) +
        (FUT.ledger.first_as_of ? ' Logging began ' + esc(FUT.ledger.first_as_of) + '.' : '') +
        '</p>' : '') +
      '<p class="bt-dim">' + esc(FUT.sims) + " simulations, board hash " +
      esc(FUT.content_hash) + ".</p></div>" + (on ? brPanel(ov) : "");
  }

  function renderValidation() {
    var v = vstate();
    // No subheading above the validation panel: it carries its own question
    // heading and its own gates sub-heading, and a third label here repeated
    // the second one word for word.
    var out = [honestResult(), clocksPanel()];
    out.push(validationPanel());
    // Beside the vintage Brier and the skill t, because it qualifies them
    // (owner decision 2026-09-18).
    out.push(basisPanel());
    out.push(calibrationPanel());
    out.push(benchmarkPanel());
    out.push(dispersionPanel());
    if (v && v.generated_at) {
      out.push('<div class="bt-asof">Validation state: ' +
        esc(v.artifact || "data/betting_model_eval.json") + ", generated " +
        esc(v.generated_at) + ". Clocks and calibration: " +
        esc(AUX_URL.learning) + ".</div>");
    }
    return out.join("");
  }

  // ---- section: the record --------------------------------------------------
  // THREE PANELS, and the validation accounting is no longer one of them: it
  // moved to its own tab. What is here is the record itself, the closing-line
  // grade on the positions in it, and the pre-registered list of conditions a
  // pick has to clear before it may enter the record at all.
  // ROI BY TAG (A6, 2026-08-16), horizontal SVG bars off the learning
  // artifact's shadow_by_tag block, on the Record tab BECAUSE that is where a
  // reader hunts for a track record, labelled "paper bets, not the record" in
  // the heading so the placement cannot mislead. Polarity encoding: the
  // page's own green/red for positive/negative, with the tag name and the
  // number as text on every bar, never colour alone. The tags stay separate
  // for the section 7a reason: a pooled ROI measures a mixture nobody bet.
  function roiByTagPanel() {
    var L = ((aux("learning") || {}).latest) || {};
    var byTag = L.shadow_by_tag || null;
    var rows = ['<div class="bt-panel-hd">ROI by selection rule (paper bets, ' +
                "not the record)</div>"];
    if (!byTag) {
      rows.push(chartAbsent("ROI by tag",
        (auxState("learning") === "ok"
          ? "data/betting_learning.json carries no shadow_by_tag block."
          : auxMissing("learning"))));
      return '<div class="bt-panel">' + rows.join("") + "</div>";
    }
    var keys = Object.keys(byTag).sort();
    var meas = keys.filter(function (k) { return (byTag[k] || {}).roi != null; });
    if (!meas.length) {
      rows.push(chartAbsent("ROI by tag", "no tag has a settled paper row yet."));
      return '<div class="bt-panel">' + rows.join("") + "</div>";
    }
    var maxAbs = 0;
    meas.forEach(function (k) {
      maxAbs = Math.max(maxAbs, Math.abs(byTag[k].roi));
    });
    maxAbs = maxAbs || 1;
    var W = 340, RH = 22, LBL = 96, MID = LBL + (W - LBL) / 2;
    var H = meas.length * RH + 16;
    var s = ['<svg class="bt-svg bt-svg-roi" viewBox="0 0 ' + (W + 60) + " " + H +
             '" role="img" aria-label="paper-bet ROI per selection rule">'];
    s.push('<line class="bt-svg-grid" x1="' + MID + '" y1="2" x2="' + MID +
           '" y2="' + (H - 14) + '"/>');
    s.push('<text class="bt-svg-axis" x="' + MID + '" y="' + (H - 4) +
           '" text-anchor="middle">0%</text>');
    meas.forEach(function (k, i) {
      var t = byTag[k];
      var y = i * RH + 3;
      var half = (W - LBL) / 2 - 2;
      var w = Math.min(half, Math.abs(t.roi) / maxAbs * half);
      var x = t.roi < 0 ? MID - w : MID;
      var tip = k + ": " + t.won + "-" + t.lost + (t.push ? "-" + t.push : "") +
        ", " + signed(t.net_units, 2) + "u, ROI " + pct(t.roi, 1) +
        " on " + t.n_settled + " settled paper bets";
      s.push('<text class="bt-svg-axis" x="' + (LBL - 4) + '" y="' + (y + RH / 2 + 2) +
             '" text-anchor="end">' + esc(k) + "</text>");
      s.push('<rect class="' + (t.roi < 0 ? "bt-svg-neg" : "bt-svg-pos") +
             '" x="' + x.toFixed(1) + '" y="' + y + '" width="' +
             Math.max(1, w).toFixed(1) + '" height="' + (RH - 5) +
             '"><title>' + esc(tip) + "</title></rect>");
      s.push('<text class="bt-svg-axis" x="' + (W + 4) + '" y="' + (y + RH / 2 + 2) +
             '">' + esc(pct(t.roi, 1)) + "</text>");
    });
    s.push("</svg>");
    rows.push('<div class="bt-chart">' + s.join("") + "</div>");
    rows.push(note("<strong>Paper bets, not the record.</strong> Settled " +
      gl("shadow ledger", "shadow_ledger") + " rows per selection rule at board " +
      "prices; none was a published " + selNoun() + ". Tags are never pooled: a " +
      "combined ROI measures a mixture nobody bet."));
    return '<div class="bt-panel">' + rows.join("") + "</div>";
  }

  // ONE READ OF THE SERVED CLV SWITCH (betting_export.SERVE_CLV, owner
  // 2026-09-07). Absent reads as OFF: a payload that does not carry the flag is
  // one that cannot have CLV data either, and an empty panel is the defect this
  // retirement removes.
  function clvEnabled() {
    return !!((S.data || {}).serve_clv);
  }

  function renderRecord() {
    var d = S.data;
    // CLV RETIRED (betting_export.SERVE_CLV, owner 2026-09-07). Read off the
    // payload, never a literal here, so the server flag moves the panel and the
    // copy below together.
    var clvOn = clvEnabled();
    return recordPanel(d ? d.record : null) + (clvOn ? clvPanel() : "") + roiByTagPanel() +
      publishBlockerPanel() +
      '<div class="bt-panel"><div class="bt-panel-hd">How a ' + selNoun() +
      " gets graded</div>" +
      "<p>Each published " + selNoun() + " records the timestamp, book, price at " +
      "post and a flat 1 " + gl("unit", "betting_unit") +
      ", and settles won, lost or void.</p>" +
      (clvOn
        ? "<p>It is also graded against the closing line (" +
          gl("closing line value", "clv") + "): beating the close means the market " +
          "moved toward it after posting. Price CLV is the posted decimal over the " +
          "closing decimal, minus 1; probability CLV is the implied probability at " +
          "close minus at post; beat-close rate is the share that beat it. A won bet " +
          "alone is not evidence.</p>"
        : "<p><strong>Graded on realized results only.</strong> " +
          gl("Closing line value", "clv") + " was retired on 2026-09-07: no closing " +
          "snapshot was ever captured. Results are noisier than CLV, and one season " +
          "is a small sample.</p>") + "</div>";
  }

  function chip(label, value) {
    return '<span class="bt-numchip"><span class="bt-numchip-l">' + esc(label) +
      '</span><span class="bt-numchip-v">' + esc(value) + "</span></span>";
  }

  // The graded blocks, mode labels attached. `model.validation.graded_blocks`
  // is the shaped list betting_export builds; the raw backtest object is the
  // fallback for a payload built before that key existed, and its rows may
  // carry no mode at all, which the table prints as unknown rather than
  // guessing.
  function backtestBlocks(m) {
    var v = (m || {}).validation;
    if (v && v.graded_blocks && v.graded_blocks.length) return v.graded_blocks;
    var bt = (m || {}).backtest || {};
    return [bt.in_sample, bt.forward, bt.vintage].filter(Boolean);
  }

  // Beating a baseline on the point estimate and beating it significantly are
  // two different claims. The page used to make the first and let it read as
  // the second. The forward split's paired-Brier t is in the payload, so the
  // sentence states both or neither.
  function skillSentence(blocks) {
    var fwd = null, i;
    for (i = 0; i < blocks.length; i++) {
      if (blocks[i].key === "forward" || /^forward/.test(String(blocks[i].label || ""))) {
        fwd = blocks[i];
      }
    }
    var sk = fwd && fwd.skill_vs_home_base;
    // No claim about which baselines a block beats is typed here: the table
    // above carries every Brier, and a sentence asserting the comparison would
    // outlive the numbers it describes.
    if (!sk || sk.t == null) {
      return "Point estimates, not significance tests.";
    }
    var head = "Forward split: " + signed(sk.delta, 6) + " Brier skill over the " +
      "home-field baseline at t = " + num(sk.t, 2) + ", which ";
    if (sk.beats_baseline_95) {
      return head + "clears the one-sided 95% bar of 1.645.";
    }
    return head + "does NOT clear the one-sided 95% bar of 1.645 (needs about " +
      (sk.n_for_95 == null ? "more" : sk.n_for_95) + " games; the split has " +
      (fwd.n == null ? "fewer" : fwd.n) + ").";
  }

  function modelPanel(m) {
    var bt = m.backtest || {};
    var rows = [];
    rows.push('<div class="bt-panel-hd">How the number is made</div>');
    rows.push("<p>Inputs: team " + gl("Offense+", "offense_plus") + " (" +
      gl("HEM+", "hem_plus") + " rollup), team " + gl("Bullpen+", "bullpen_plus") + " (" +
      gl("REM+", "rem_plus") + "), the listed starter's " + gl("SEM+", "sem_plus") +
      " for a starter's share of innings, the park run index, and home field. Expected " +
      "runs feed a Poisson-difference margin that prices the " +
      gl("moneyline", "moneyline") + ", " + gl("runline", "runline") + " and " +
      gl("total", "total_line") + ".</p>");
    if (m.coefficients) {
      var c = m.coefficients;
      rows.push('<div class="bt-kv">' +
        kv("Runs per sigma of offense", num(c.b1, 3)) +
        kv("Runs per sigma of opposing prevention", num(c.b2, 3)) +
        kv("Park pass-through", num(c.b3, 2)) +
        kv("Coefficient source", esc(c.source || "-")) +
        kv("Fit rows", c.n_rows || "-") + "</div>");
    }
    if (m.league_context && m.league_context.n_games) {
      var lc = m.league_context;
      rows.push('<div class="bt-kv">' +
        kv("Season games measured", lc.n_games) +
        kv("League runs per team per game", num(lc.lg_rpg, 2)) +
        kv("Home win rate", pct(lc.home_win_rate)) +
        kv("Extra innings, home rate", pct(lc.extra_inning_home_rate)) + "</div>");
    }
    var blocks = backtestBlocks(m);
    if (blocks.length) {
      rows.push('<div class="bt-panel-sub">' + gl("Backtest", "backtest") +
        ", and why it does not count</div>");
      rows.push("<p>" + esc(bt.contamination || "") + "</p>");
      // EVERY row names the mode that produced it. Two of these blocks are
      // contaminated and one is honest, they are not comparable, and a table
      // that stacks them without the label invites the reader to read the
      // wrong number as the result.
      rows.push('<div class="bt-scroll mlbstats-scroll"><table class="bt-table mlbstats-table"><thead><tr><th class="bt-l">Test</th>' +
        "<th>Mode</th><th>Games</th>" +
        "<th>Brier</th><th>vs flat .500</th><th>vs home base</th><th>Accuracy</th></tr></thead><tbody>" +
        blocks.map(function (b) {
          var n = (b.n != null) ? b.n : b.n_graded;
          return "<tr><td class=\"bt-l\">" + esc(b.label || b.key || "") +
            (b.status && b.status !== "graded"
              ? ' <span class="bt-dim">' + esc(b.status) + "</span>" : "") +
            "</td><td>" + modeTag(b.mode, b.honest) + "</td><td>" + (n == null ? "-" : n) +
            "</td><td>" + num(b.brier, 5) + "</td><td>" + num(b.brier_flat_500, 5) + "</td><td>" +
            num(b.brier_home_base, 5) + "</td><td>" + pct(b.accuracy) + "</td></tr>";
        }).join("") + "</tbody></table></div>");
      rows.push(note("Lower " + gl("Brier", "brier_score") + " is better. " + skillSentence(blocks) +
        " Contaminated rows use season-to-date inputs, so every graded game sits inside " +
        "its own features; they validate nothing. " + esc(bt.note || "")));
    }
    if (m.known_limits && m.known_limits.length) {
      rows.push('<div class="bt-panel-sub">Known limits</div><ul class="bt-list">' +
        m.known_limits.map(function (x) { return "<li>" + esc(x) + "</li>"; }).join("") + "</ul>");
    }
    return '<div class="bt-panel">' + rows.join("") + "</div>";
  }

  function kv(k, v) {
    return '<div class="bt-kv-row"><span class="bt-kv-k">' + esc(k) +
      '</span><span class="bt-kv-v">' + v + "</span></div>";
  }

  // THE POSTSEASON SUB-LEDGER (owner decision 2026-10-01). The headline above
  // it counts regular-season rows only and says so; postseason rows are
  // tallied here and added to nothing. A payload from before the split carries
  // no `postseason` block and renders exactly as it did.
  function postseasonRecordBlock(r) {
    var ps = (r || {}).postseason;
    if (!ps) return "";
    var lbl = esc(ps.label || "never graded on a postseason game");
    var head = '<div class="bt-panel-sub">Postseason sub-ledger (' + lbl + ")</div>";
    if (!ps.n_rows) {
      return head + "<p>No postseason row on the record yet. A postseason " + selNoun() +
        " lands here, labelled, and never in the regular-season counts above.</p>";
    }
    return head + '<div class="bt-kv">' +
      kv("Record", ps.won + "-" + ps.lost + (ps.push ? "-" + ps.push : "")) +
      kv("Net units", signed(ps.net_units, 2)) +
      kv("ROI", ps.roi_pct == null ? "-" : signed(ps.roi_pct, 2) + "%") +
      kv("Open", ps.n_open) + "</div>" +
      (ps.note ? note(esc(ps.note)) : "");
  }

  function recordPanel(r) {
    var body;
    var nAll = r ? (r.n_rows_all != null ? r.n_rows_all : r.n_rows) : 0;
    if (!r || !nAll) {
      body = empty("The record starts when the " + selNounPl() + " do",
        "No " + selNoun() + " published yet. Each lands here with its book, price " +
        "at post and a flat 1 unit stake" +
        (clvEnabled() ? ", graded against the closing line" : "") +
        ". Rows are never edited or deleted.");
    } else {
      body = (r.postseason ? '<div class="bt-panel-sub">Regular season</div>' : "") +
        '<div class="bt-kv">' +
        kv("Record", r.won + "-" + r.lost + (r.push ? "-" + r.push : "")) +
        kv("Net units", signed(r.net_units, 2)) +
        kv("ROI", r.roi_pct == null ? "-" : signed(r.roi_pct, 2) + "%") +
        // The two CLV cells ride the same served switch as the panel. Left in
        // unconditionally they printed "not graded yet" forever, which is how a
        // permanently absent instrument reads as a pending one.
        (clvEnabled()
          ? kv("Beat close", r.beat_close_rate == null ? "not graded yet" : pct(r.beat_close_rate)) +
            kv("Average CLV", r.avg_clv_pct == null ? "not graded yet" : signed(r.avg_clv_pct, 2) + "%")
          : "") +
        kv("Open", r.n_open) +
        "</div>" +
        (r.scope_note ? note(esc(r.scope_note)) : "") +
        postseasonRecordBlock(r);
    }
    var url = (S.data && S.data.record_url) || "/data/betting_record.json";
    // THE JOIN, NAMED. `record` is not the record file: it is the record joined
    // to the settlement sidecar and to the CLV sidecar on bet_id. Neither
    // `beat_close` nor `clv_pct` can ever be a byte of a record row, because
    // rows are immutable and CLV lands hours later, so a summary computed off
    // the record alone reported "not graded yet" over a fully graded record.
    var sha = (r || {}).chain_sha;
    var chain = sha ? ('<div class="bt-clock-fine">Chain ' +
      '<code class="bt-sha">' + esc(sha) + "</code>. " +
      esc((r || {}).chain_note || "") + " Archive it: a later record whose prefix " +
      "hashes include it is an append; one without it is a rewrite.</div>") : "";
    // THE JOIN FOLLOWS THE SERVED FLAG (M12-04, 2026-09-25). With CLV retired
    // (serve_clv false) no closing-line sidecar is written, so the sentence
    // names two files and links the settlement sidecar alone; the third file
    // and its link return with the flag.
    var clvOn = clvEnabled();
    var setUrl = (S.data && S.data.settlement_url) || "/data/betting_settlement.json";
    var clvUrl = (S.data && S.data.clv_url) || AUX_URL.clv;
    var setLink = '<a class="bt-link" href="' + esc(setUrl) + '">' + esc(setUrl) + "</a>";
    return '<div class="bt-panel"><div class="bt-panel-hd">The public record</div>' + body +
      (clvOn
        ? "<p>Joined across three files on bet_id: the append-only record, the settlement " +
          "sidecar and the closing-line sidecar."
        : "<p>Joined across two files on bet_id: the append-only record and the settlement " +
          "sidecar.") +
      " To verify, recompute the chain by " +
      "folding sha256 row by row over " + esc(url) + " and compare to the hash " +
      "below.</p>" + chain +
      "<p>" + esc((S.data && S.data.record_policy) ||
        "Append only. Rows are never edited or deleted; a correction is a new row.") + " " +
      'Raw file: <a class="bt-link" href="' + esc(url) + '">' + esc(url) + "</a>. " +
      (clvOn
        ? "Sidecars: " + setLink + " and " +
          '<a class="bt-link" href="' + esc(clvUrl) + '">' + esc(clvUrl) + "</a>.</p></div>"
        : "Sidecar: " + setLink + ".</p></div>");
  }

  // ---- CLV, and the reasons it graded nothing -------------------------------
  // Beating the close is the only honest read on an unvalidated model's
  // decisions, so an empty CLV panel has to say WHY it is empty. The sidecar
  // publishes `ungraded_reasons` as a count per reason; when there is nothing
  // to plot, that dictionary IS the content.
  function clvDeciles(picks) {
    var vals = (picks || []).map(function (p) {
      return (p && p.graded && typeof p.clv_pct === "number") ? p.clv_pct : null;
    }).filter(function (x) { return x != null; });
    if (!vals.length) return null;
    var lo = Math.min.apply(null, vals), hi = Math.max.apply(null, vals);
    var span = (hi - lo) || 1;
    var bins = [], i;
    for (i = 0; i < 10; i++) bins.push(0);
    vals.forEach(function (x) {
      var k = Math.floor(((x - lo) / span) * 10);
      if (k > 9) k = 9;
      if (k < 0) k = 0;
      bins[k] += 1;
    });
    return { lo: lo, hi: hi, bins: bins, n: vals.length,
             max: Math.max.apply(null, bins) };
  }

  function clvPanel() {
    var r = (S.data && S.data.record) || {};
    // THE SIDECAR IS ONLY FETCHED ONCE THERE IS SOMETHING FOR IT TO GRADE. It
    // is derived from the record, so on an empty record it does not exist and
    // asking for it would put a 404 in every reader's console (and fail
    // tools/verify_site.py, which treats a console error as a broken route)
    // to learn what the record already says.
    var side = (r.n_rows ? aux("clv") : null);
    var rows = ['<div class="bt-panel-hd">' + gl("Closing line value", "clv") + "</div>"];
    rows.push('<div class="bt-kv">' +
      kv("Graded against the close", r.n_clv_graded == null ? "-" : r.n_clv_graded) +
      kv("Beat close", r.beat_close_rate == null ? "not graded yet" : pct(r.beat_close_rate)) +
      kv("Mean CLV", r.avg_clv_pct == null ? "not graded yet" : signed(r.avg_clv_pct, 2) + "%") +
      "</div>");
    var h = side ? clvDeciles(side.picks) : null;
    if (h) {
      rows.push('<div class="bt-panel-sub">Distribution, ' + h.n + " graded " +
        selNounPl() + " in ten " +
        "equal-width bins from " + signed(h.lo, 2) + "% to " + signed(h.hi, 2) + "%</div>");
      rows.push('<div class="bt-scroll mlbstats-scroll"><table class="bt-table mlbstats-table">' +
        '<thead><tr><th class="bt-l">Bin</th><th class="bt-l">Count</th><th>n</th>' +
        "</tr></thead><tbody>" +
        h.bins.map(function (c, i) {
          var lo = h.lo + (h.hi - h.lo) * (i / 10), hi2 = h.lo + (h.hi - h.lo) * ((i + 1) / 10);
          var w = h.max ? (100 * c / h.max) : 0;
          return '<tr><td class="bt-l">' + signed(lo, 2) + "% to " + signed(hi2, 2) +
            '%</td><td class="bt-l"><span class="bt-bar" style="width:' + w.toFixed(1) +
            '%"></span></td><td>' + c + "</td></tr>";
        }).join("") + "</tbody></table></div>");
    } else {
      var reasons = (side && side.ungraded_reasons) || null;
      if (reasons) {
        var keys = Object.keys(reasons).sort();
        rows.push("<p>No closing-line grades. Rows by reason:</p>");
        rows.push('<div class="bt-scroll mlbstats-scroll"><table class="bt-table mlbstats-table">' +
          '<thead><tr><th class="bt-l">Reason</th><th>Rows</th></tr></thead><tbody>' +
          keys.map(function (k) {
            return '<tr><td class="bt-l">' + esc(k) + "</td><td>" + reasons[k] + "</td></tr>";
          }).join("") + "</tbody></table></div>");
      } else if (!r.n_rows) {
        rows.push("<p>No " + selNoun() + " published, so nothing to grade against a " +
          "close.</p>");
      } else {
        rows.push("<p>No closing-line grades. " + esc(auxMissing("clv")) + "</p>");
      }
      rows.push(note("CLV is unrecoverable after the fact: a slate whose close was never " +
        "captured can never be graded. Repair: install the close cron " +
        "(deploy/betting-crontab.example via crontab -e, or " +
        "deploy\\betting-close-task.ps1 -Register on Windows) and check it with " +
        "<code>python tools/betting_close_job.py --selfcheck</code>; NEVER RUN means " +
        "no cron or task is installed."));
    }
    return '<div class="bt-panel">' + rows.join("") + "</div>";
  }

  // ---- what actually gates the first published row --------------------------
  // Pre-registered and shipped whether it passes or not: the list is a claim
  // about what this site refuses to publish, and a reader can only hold it to
  // that if he can read it BEFORE the first row exists.
  function publishBlockerPanel() {
    var d = S.data || {};
    var bl = d.record_publish_blockers || null;
    var pub = d.record_publish || {};
    var rows = ['<div class="bt-panel-hd">What gates the first published row</div>'];
    if (!bl || !bl.length) {
      rows.push("<p>This payload predates the publish-blocker list.</p>");
      return '<div class="bt-panel">' + rows.join("") + "</div>";
    }
    var nOpen = 0;
    bl.forEach(function (b) { if (b.open) nOpen += 1; });
    rows.push("<p>" + nOpen + " of " + bl.length + " are open. A " + selNoun() +
      " is written to the public record only when all are.</p>");
    rows.push('<div class="bt-scroll mlbstats-scroll"><table class="bt-table mlbstats-table">' +
      '<thead><tr><th class="bt-l">Blocker</th><th class="bt-l">What it needs</th>' +
      '<th class="bt-l">Have</th><th>State</th></tr></thead><tbody>' +
      bl.map(function (b) {
        var have = b.have;
        if (have && typeof have === "object") {
          have = Object.keys(have).map(function (k) {
            var x = have[k];
            return k + " " + (x == null ? "none" : String(x).slice(0, 16));
          }).join(", ");
        }
        return '<tr><td class="bt-l">' + esc(b.id) + '</td><td class="bt-l bt-gate-need">' +
          esc(b.need || "") + whyBlock(b.reason, "why this blocker exists") +
          '</td><td class="bt-l">' +
          esc(have == null ? "-" : String(have)) + "</td><td>" +
          '<span class="bt-tag ' + (b.open ? "bt-tag-ok" : "bt-tag-warn") + '">' +
          (b.open ? "open" : "closed") + "</span></td></tr>";
      }).join("") + "</tbody></table></div>");
    if (pub.reason) rows.push(note("This build: " + esc(pub.reason) + "."));
    return '<div class="bt-panel">' + rows.join("") + "</div>";
  }

  // ---- section: team bets ---------------------------------------------------
  // ---- all-bets leaderboard (owner ask 2026-09-07) --------------------------
  var TEAM_VIEW_KEY = "eephus.betting.teamview";

  function teamView() {
    if (S.teamView) return S.teamView;
    try { S.teamView = localStorage.getItem(TEAM_VIEW_KEY) || "cards"; }
    catch (e) { S.teamView = "cards"; }
    return S.teamView;
  }

  function teamViewToggle() {
    var v = teamView();
    function b(id, label, title) {
      return '<button type="button" class="bt-seg-btn' + (v === id ? " is-on" : "") +
        '" data-teamview="' + id + '" aria-pressed="' + (v === id ? "true" : "false") +
        '" title="' + esc(title) + '">' + esc(label) + "</button>";
    }
    return '<div class="bt-seg" role="group" aria-label="Team bets view">' +
      b("cards", "Game cards", "One panel per game, all three markets together") +
      b("board", "All bets", "Every bet on the slate in one sortable table") +
      "</div>";
  }

  // Every leg on the board, flattened. One row per side of every market, with
  // the game it came from, so the table can be sorted across games.
  function allBetLegs(bets) {
    var out = [];
    (bets || []).forEach(function (b) {
      var game = ((b.away || {}).org || "?") + " at " + ((b.home || {}).org || "?");
      function push(market, marketLabel, rows) {
        (rows || []).forEach(function (r) {
          if (!r) return;
          out.push({ game: game, start: b.start, market: market,
                     marketLabel: marketLabel, r: r });
        });
      }
      push("moneyline", "Moneyline", b.moneyline);
      push("runline", "Run line", b.runline);
      push("total", "Total", (b.total || {}).sides);
    });
    return out;
  }

  function allBetsTable(bets) {
    var legs = allBetLegs(bets);
    if (!legs.length) return "";
    var thr = pickFloor();
    var cols = [
      ["Game", "the matchup, away at home"],
      ["Market", "moneyline, run line or total"],
      ["Bet", "the side and the number"],
      ["Book", "the book posting the price used here"],
      ["Odds", "the price on offer, American"],
      ["Model", "the model's probability for this side"],
      ["Fair", "the price the model's probability implies, American"],
      ["Market", "the book's probability with the vig removed"],
      ["Edge", "model probability minus de-vigged market probability"],
      ["EV/unit", "expected profit per unit staked at this price"],
      ["Kelly", "full Kelly stake fraction; the site stakes a flat unit"]
    ];
    var head = cols.map(function (c) {
      return '<th scope="col" title="' + esc(c[1]) + '">' + esc(c[0]) + "</th>";
    }).join("");
    var body = legs.map(function (L) {
      var r = L.r;
      var clears = (thr != null && r.edge != null && r.edge >= thr &&
                    r.odds != null && r.book);
      // data-sort on the numeric cells so the parser never has to guess at a
      // formatted string, and so an unpriced leg sorts as null rather than as 0.
      function num(v, txt) {
        return '<td class="bt-num"' + (v == null ? "" : ' data-sort="' + v + '"') +
          ">" + txt + "</td>";
      }
      var plain = clears && badgePlain(r);
      return '<tr' + (clears ? ' class="bt-row-value' + (plain ? " bt-row-plain" : "") + '"' : "") + ">" +
        "<td>" + esc(L.game) + "</td>" +
        "<td>" + esc(L.marketLabel) + "</td>" +
        "<td>" + esc(r.label == null ? "-" : r.label) +
          (clears ? (plain ? ' <span class="bt-tag bt-tag-plain">clears floor</span>'
                           : ' <span class="bt-tag bt-tag-ok">value</span>') : "") + "</td>" +
        "<td>" + esc(r.book_title || r.book || "-") + "</td>" +
        num(r.odds, fmtOdds(r.odds)) +
        num(r.model_prob, pct(r.model_prob)) +
        num(r.fair_odds, fmtOdds(r.fair_odds)) +
        num(r.market_fair_prob, pct(r.market_fair_prob)) +
        num(r.edge, r.edge == null ? "-" : signed(r.edge * 100, 1) + "%") +
        num(r.ev_per_unit, r.ev_per_unit == null ? "-" : signed(r.ev_per_unit, 3)) +
        num(r.kelly_full, r.kelly_full == null ? "-" : (r.kelly_full * 100).toFixed(1) + "%") +
        "</tr>";
    }).join("");
    var n_priced = legs.filter(function (L) { return L.r.odds != null; }).length;
    return '<div class="bt-panel"><div class="bt-panel-hd">Every bet on the board</div>' +
      "<p>" + legs.length + " bet(s) across " + (bets || []).length + " game(s), " +
      n_priced + " with a posted price. Unpriced legs stay and sort last.</p>" +
      (thr == null
        ? note("No floor is in force, so nothing is badged. " + floorAbsentReason())
        : "") +
      '<div class="bt-scroll mlbstats-scroll"><table class="bt-table mlbstats-table" data-sort-key="teams:allbets" ' +
      'data-default-sort="8:desc"><thead><tr>' + head + "</tr></thead><tbody>" +
      body + "</tbody></table></div></div>";
  }

  // Exposed for tests, the same way the sort parser and comparator are: both
  // are pure functions of the board rows, and driving them directly is how a
  // test asserts the leaderboard's CONTENT without a DOM to click a toggle in.
  if (typeof window !== "undefined") {
    window.EEPHUS_BETTING_BOARD = {
      legs: function (bets) { return allBetLegs(bets); },
      table: function (bets) { return allBetsTable(bets); },
      // The SERVED floor, the one the badge reads, so a test asserts against
      // the same number rather than a second copy of the rule.
      floor: function () { return pickFloor(); }
    };
    // The loaded payload, read-only, so a test can drive the two pure functions
    // above against the SAME rows the page rendered rather than a copy.
    window.EEPHUS_BETTING_STATE = function () { return S; };
  }

  // Why there is no bar to clear, in the words the rest of the page uses.
  function floorAbsentReason() {
    var m = (S.data && S.data.pick_meta) || {};
    if (m.blocked) return String(m.blocked_reason || "The slots are blocked for this build.");
    return "The model has no measured minimum edge yet.";
  }

  function renderTeam() {
    var d = S.data;
    if (!d) return empty("No slate loaded", "The betting payload has not been built yet.");
    var bets = d.team_bets || [];
    if (!bets.length) {
      return empty("No games priced",
        ((d.status && d.status.empty_reasons) || []).join(". ") ||
        "The schedule has not been refreshed today.");
    }
    var hasMarket = (d.status || {}).odds_feed === "ok";
    var reason = (d.status || {}).odds_note || "";
    var head = hasMarket ? "" : note("No odds feed: model fair prices only." +
      (reason ? " Build: " + esc(reason) + "." : ""));
    // AN ABSENT ROW READS AS AN ABSENT GAME. Two filters can leave a scheduled
    // game with no prices: the odds event was already under way (an in-game
    // price is real, it is just not this bet), or no event started within the
    // match window of first pitch (past that, a single candidate is a different
    // game in the same series). Both counts ship on `status`; the games
    // themselves stay on the board carrying the reason.
    var st2 = d.status || {};
    var nDrop = st2.n_events_dropped_in_progress, nMiss = st2.n_games_unpriced_time_mismatch;
    if (hasMarket && (nDrop || nMiss)) {
      head += note("<strong>" + ((nDrop || 0) + (nMiss || 0)) + " odds events did not " +
        "price a game.</strong> " + (nDrop || 0) + " were already under way at snapshot " +
        "time; " + (nMiss || 0) + " had a candidate event too far from first pitch to be " +
        "the same game. Those games stay on the board, marked unpriced.");
    }
    // 2026-08-16: pick_meta.blocked was read by pickCensus alone, so a build
    // whose slots the server hard-stopped still handed out green badges off
    // the surviving min_edge (the server fills meta before the block branch).
    // The reason prints here, above the board, and pickFloor treats the block
    // as no floor, so the badge and its head note go down with the picks they
    // claim agreement with.
    var meta = d.pick_meta || {};
    if (meta.blocked) {
      head += note("<strong>No " + badgeWord(null) + " badges today.</strong> " +
        esc(meta.blocked_reason || "the selection rule never ran") +
        ". The " + selNoun() + " slots stopped for that reason, and the badge " +
        "stops with them.");
    }
    var thr = pickFloor();
    if (hasMarket && thr != null) {
      // THE BADGE IS THE EDGE FLOOR AND NOTHING ELSE (repaired 2026-09-18).
      // Whether that is ALSO the bar the slots use depends on the slot market
      // policy: where no leg bars, the two are the same bar; where a leg bars,
      // the slots drop whole markets this badge still marks, so "the bar the
      // picks use" would be false. The sentence reads the served legs through
      // `policyLegs` rather than assuming the value shipped today.
      var pl = policyLegs();
      var whose = !pl.known
        ? ". This payload does not say whether the " + selNounPl() +
          " apply a further market rule"
        : (pl.bars
          ? ", the edge floor alone. The " + selNounPl() + " also drop any market " +
            "the slot policy bars, so a badge is not a claim of eligibility"
          : ", the bar the " + selNounPl() + " use");
      head += note("A <strong>" + badgeWord(null) + "</strong> badge marks the side in each game " +
        "with the largest " + gl("edge", "bet_edge") + " clearing " +
        esc(floorText((S.data && S.data.pick_meta) || {})) + whose +
        ". No badge: nothing in that game cleared it." +
        (watchMode() ? " The model is unvalidated, so the badge is a measured gap, not a value call." : "") +
        (!watchMode() && d.total_level_check && d.total_level_check.fires
          ? " A total that leans with the whole slate reads largest gap in plain ink: its row " +
            "says the lean is model shape, not value."
          : ""));
    }
    // The both-legs copy state renders above the board too: the closed
    // market's rows stay priced below (the ledgers keep recording it), and a
    // reader of this tab is owed the same two reasons the watch tab states.
    head += marketGateNotes();
    // BET1: when the slate's totals lean one way past the tolerance, the
    // server's sentence says why before any total badge below is read.
    var tlc = d.total_level_check || {};
    if (hasMarket && tlc.fires && tlc.caveat) {
      head += note("<strong>Totals lean " + esc(tlc.direction || "") + " on this " +
        "slate.</strong> " + esc(tlc.caveat));
    }
    // TWO VIEWS OVER THE SAME ROWS. The toggle rides above both, so the notes
    // and warnings above (unpriced counts, missing feed, blocked slots) are
    // shown once and apply to whichever view is up.
    var view = teamView();
    // Dugout context dark state, once, under the notes, cards view only: the
    // all-bets board view is a row table and carries no management figure.
    if (view !== "board") head += dugoutDarkNote();
    return head + teamViewToggle() +
      (view === "board" ? allBetsTable(bets) : bets.map(gameCard).join(""));
  }

  // THE BADGE AND THE PICKS READ ONE NUMBER. The threshold comes from
  // `pick_meta.min_edge`, which is the same resolved floor the server used to
  // choose the slots, so a row can never be badged as value on the board while
  // being below the bar the picks were held to. Hard-coding it here is how the
  // two would drift the day the measured threshold replaces the policy floor.
  function pickFloor() {
    var m = (S.data && S.data.pick_meta) || {};
    // 2026-08-16: a blocked build keeps its min_edge, so reading the floor
    // alone let the badge outlive the stop that emptied both pick slots.
    // Blocked means there is no bar to clear, not a bar that was cleared.
    if (m.blocked) return null;
    return (m.min_edge == null) ? null : Number(m.min_edge);
  }

  // The single best-value side in one game, or null when nothing clears the
  // floor. Absence is the message: a game with no qualifying side gets no badge
  // rather than a badge on its least-bad row.
  function bestValueSide(b, thr) {
    if (thr == null) return null;
    var best = null;
    [b.moneyline, b.runline, (b.total || {}).sides].forEach(function (rows) {
      (rows || []).forEach(function (r) {
        if (r.edge == null || r.edge < thr || r.odds == null || !r.book) return;
        if (!best || r.edge > best.edge) best = r;
      });
    });
    return best;
  }

  // THE BADGE'S WORD AND INK FOLLOW WHAT THE ROW CAN STAND BEHIND (M12-02,
  // 2026-09-25). A green "best value" tag sat on total Overs whose own row says
  // "Known model shape, not value", on a board served under the watch frame,
  // which retired the pick noun (owner decision 2026-08-16). The tag still
  // marks the same side (bestValueSide is untouched, so no slot, record, gate
  // or policy leg moves); only the words and the colour change. Under the
  // watch frame, and on any side carrying total_level_caveat, it reads
  // "largest gap" in plain ink; green "best value" returns under the pick
  // frame on rows the slate-lean check does not caveat.
  function badgePlain(r) { return watchMode() || !!(r && r.total_level_caveat); }
  function badgeWord(r) { return badgePlain(r) ? "largest gap" : "best value"; }
  function badgeTag(r, tail) {
    return ' <span class="bt-tag ' + (badgePlain(r) ? "bt-tag-plain" : "bt-tag-ok") +
      ' bt-bestval">' + badgeWord(r) + (tail ? " " + tail : "") + "</span>";
  }

  // The match window, in minutes. MIRRORS betting_export.EVENT_MATCH_MAX_MINUTES
  // and is read from the payload the moment `status` carries it; the literal is
  // the fallback for a payload that does not, and it exists only so the reason
  // on an unpriced row is a number rather than a shrug.
  function matchWindowText(st) {
    var mins = (st && st.event_match_max_minutes != null)
      ? Number(st.event_match_max_minutes) : 180;
    return (mins % 60 === 0) ? (mins / 60) + "h" : mins + " min";
  }

  // The postseason label, read off a card, a slot or a record row. Empty for a
  // regular-season row, which carries no game_type at all.
  function postseasonLabel(r) {
    if (!r || !r.game_type || r.game_type === "R") return "";
    return String(r.postseason_label || "never graded on a postseason game");
  }

  function postseasonTag(r) {
    var lbl = postseasonLabel(r);
    if (!lbl) return "";
    return ' <span class="bt-tag bt-tag-warn bt-post" title="' +
      esc((r.series ? r.series + ": " : "") + "the model was fitted and graded " +
        "on regular-season games only") + '">' + esc(lbl) + "</span>";
  }

  function gameCard(b) {
    var m = b.model || {};
    var st = (S.data || {}).status || {};
    var best = bestValueSide(b, pickFloor());
    var badge = best ? badgeTag(best, esc(best.label || best.side || "") + " " +
      fmtOdds(best.odds)) : "";
    if (gameStarted(b)) badge += ' <span class="bt-tag bt-tag-warn bt-started">started</span>';
    // BET1: a best-value badge on a total that leans with the whole slate
    // carries the lean, so the badge cannot be read without it.
    if (best && best.total_level_caveat) {
      badge += ' <span class="bt-tag bt-tag-warn bt-totlean" title="' +
        esc(best.total_level_caveat) + '">slate lean</span>';
    }
    // UNPRICED IS A STATE, NOT AN OMISSION. The board carries the game and says
    // which filter left it without prices, because a game that vanished off the
    // page reads as a game that is not being played.
    if (st.odds_feed === "ok" && !b.odds_event_id && !b.market) {
      badge += ' <span class="bt-tag bt-tag-warn bt-unpriced" title="' +
        esc("The candidate odds event was in progress or too far from first pitch.") +
        '">unpriced: no pre-game odds event within ' + matchWindowText(st) +
        " of first pitch</span>";
    }
    // A POSTSEASON CARD SAYS SO IN WORDS (owner decision 2026-10-01). The label
    // is the server's string, carried on the card, so the page and the record
    // read one sentence.
    badge += postseasonTag(b);
    var hd = '<div class="bt-game-hd">' +
      '<div class="bt-game-teams">' + teamLogo(b.away.org) + " " + esc(b.away.org) +
      ' <span class="bt-at">at</span> ' + teamLogo(b.home.org) + " " + esc(b.home.org) +
      badge + "</div>" +
      '<div class="bt-game-sub">' + esc(b.venue || "") +
      (b.start ? " &middot; " + esc(String(b.start).slice(11, 16)) + " UTC" : "") + "</div></div>";

    var probs = '<div class="bt-game-probs">' +
      chip(esc(b.away.org), pct(m.p_away)) + chip(esc(b.home.org), pct(m.p_home)) +
      chip("Fair total", num(m.fair_total, 2)) +
      chip("Park", num(m.park_index, 2)) + "</div>";

    var sp = '<div class="bt-game-sp">' +
      spLine(b.away, m.away_prevention) + spLine(b.home, m.home_prevention) + "</div>";

    var blocks = [marketBlock(gl("Moneyline", "moneyline"), b.moneyline, best)];
    if (b.runline) blocks.push(marketBlock(gl("Runline", "runline"), b.runline, best));
    if (b.total && b.total.sides) {
      blocks.push(marketBlock(gl("Total", "total_line") + " " + esc(b.total.line),
                              b.total.sides, best, b.total));
    }
    else blocks.push('<div class="bt-market"><div class="bt-market-hd">Total</div>' +
      '<div class="bt-faironly">Model fair total ' + num(m.fair_total, 2) +
      ". No posted line to compare.</div></div>");

    return '<div class="bt-game">' + hd + probs + sp +
      '<div class="bt-markets">' + blocks.join("") + "</div>" + devigPanel(b) +
      dugoutBlock(b.game_pk) + "</div>";
  }

  // WHICH BOOK SET THE DENOMINATOR OF EVERY EDGE IN THIS GAME. One book's
  // two-sided quote is de-vigged into the fair probability every edge on the
  // row is measured against, so naming it is naming the measuring stick. The
  // spread across the books that could have set it is the honest error bar on
  // that choice: a market where five books hold between 1.6% and 4.6% has a
  // fair line that moves with which one you pick.
  var MARKET_ROWS = [
    ["moneyline", "moneyline_fair_book", "moneyline_hold_pct", "moneyline_hold_range",
     "moneyline_n_books_on_line"],
    ["runline", "runline_fair_book", "runline_hold_pct", null, null],
    ["total", "total_fair_book", "total_hold_pct", "total_hold_range",
     "total_n_books_on_line"]
  ];

  function devigPanel(b) {
    var mk = b.market || null;
    if (!mk) return "";
    var rej = mk.n_books_rejected || {};
    var rows = MARKET_ROWS.map(function (spec) {
      var name = spec[0];
      var book = mk[spec[1]], hold = mk[spec[2]];
      var range = spec[3] ? mk[spec[3]] : null;
      var n = spec[4] ? mk[spec[4]] : ((rej[name] || {}).on_line);
      if (book == null && hold == null && n == null) return "";
      var r = rej[name] || {};
      var refused = [];
      if (r.hold) refused.push(r.hold + " hold");
      if (r.stale) refused.push(r.stale + " stale");
      if (r.consensus) refused.push(r.consensus + " off consensus");
      return '<tr><td class="bt-l">' + esc(name) + '</td><td class="bt-l">' +
        esc(book || "-") + "</td><td>" + num(hold, 2) + "%</td><td>" +
        (range && range.length === 2 ? num(range[0], 2) + "% to " + num(range[1], 2) + "%"
                                     : "-") +
        "</td><td>" + (n == null ? "-" : n) + '</td><td class="bt-l">' +
        (refused.length ? esc(refused.join(", ")) : "none") + "</td></tr>";
    }).join("");
    if (!rows) return "";
    return '<div class="bt-scroll mlbstats-scroll"><table class="bt-table mlbstats-table">' +
      '<thead><tr><th class="bt-l">Market</th><th class="bt-l">' +
      gl("De-vig", "devig") + ' book</th><th>' + gl("Hold", "vig") +
      "</th><th>Hold range</th><th>Books on line</th>" +
      '<th class="bt-l">Refused</th></tr></thead><tbody>' + rows +
      "</tbody></table></div>" +
      '<div class="bt-hold">Fair probabilities: proportional ' + gl("de-vig", "devig") +
      " of the named book only. Rule: " + esc(mk.fair_book_rule || "min_hold") + ".</div>";
  }

  function spLine(sideObj, prev) {
    var pp = sideObj.probable || null;
    if (!pp || !pp.mlbam) {
      return '<div class="bt-sp"><span class="bt-sp-org">' + esc(sideObj.org) +
        '</span><span class="bt-sp-name bt-dim">probable not announced</span>' +
        '<span class="bt-sp-num">rotation average</span></div>';
    }
    return '<div class="bt-sp"><span class="bt-sp-org">' + esc(sideObj.org) + "</span>" +
      '<span class="bt-sp-name">' + nameLink(pp.mlbam, pp.name) + "</span>" +
      '<span class="bt-sp-num">' + gl("SEM+", "sem_plus") + " " +
      num((prev || {}).starter_plus, 0) + " &middot; " + gl("pen", "bullpen_plus") + " " +
      num((prev || {}).bullpen_plus, 0) + "</span></div>";
  }

  // `title` arrives as ready HTML (it carries a glossary span), so it is the one
  // argument here that is not escaped. Every value from the payload still is.
  // `tot` is the total block itself and only the total call passes it: until
  // 2026-08-16 the push disclosure lived on the two pick cards alone, while
  // this table rendered the same push-discounted EV and push-conditional model
  // probability on a whole-number line and said nothing about either.
  function marketBlock(title, rows, best, tot) {
    if (!rows || !rows.length) return "";
    var hasBook = rows.some(function (r) { return r.odds != null; });
    var head = "<tr><th class=\"bt-l\">" + title + "</th><th>Model</th>" +
      (hasBook ? "<th>Price</th><th>" + gl("Fair", "fair_line") + "</th><th>" +
        gl("Edge", "bet_edge") +
        "</th><th>" + gl("EV/u", "ev_per_unit") + "</th><th>" +
        gl("Kelly", "kelly_criterion") + "</th>" : "<th>Fair price</th>") + "</tr>";
    var body = rows.map(function (r) {
      var cells = "<td class=\"bt-l\">" + esc(r.label || r.side) +
        (r === best ? badgeTag(r) : "") +
        "</td><td>" + pct(r.model_prob) + "</td>";
      if (hasBook) {
        var cls = r.edge == null ? "" : (r.edge > 0 ? " bt-pos" : " bt-neg");
        cells += "<td>" + fmtOdds(r.odds) + (r.book ? ' <span class="bt-dim">' + esc(r.book) +
          "</span>" : "") + "</td>" +
          "<td>" + pct(r.market_fair_prob) + "</td>" +
          '<td class="' + cls + '">' + (r.edge == null ? "-" : signed(r.edge * 100, 1) + "%") + "</td>" +
          '<td class="' + cls + '">' + (r.ev_per_unit == null ? "-" : signed(r.ev_per_unit, 3)) + "</td>" +
          "<td>" + (r.kelly_full == null ? "-" : pct(r.kelly_full)) + "</td>";
      } else {
        cells += "<td>" + fmtOdds(r.fair_odds) + "</td>";
      }
      return '<tr' + (r === best ? ' class="bt-bestrow"' : "") + ">" + cells + "</tr>";
    }).join("");
    var push = "";
    if (tot) {
      var pp = (tot.p_push != null) ? tot.p_push
                                    : (((tot.sides || [])[0] || {}).p_push);
      var pline = pushText({ p_push: pp,
                             point: (tot.line != null ? Number(tot.line) : null) },
                           "the Model column", "the EV/u column");
      if (pline) push = '<div class="bt-hold">' + pline + "</div>";
    }
    return '<div class="bt-market"><div class="bt-scroll mlbstats-scroll"><table class="bt-table bt-market-table mlbstats-table">' +
      "<thead>" + head + "</thead><tbody>" + body + "</tbody></table></div>" + push + "</div>";
  }

  // ---- section: props -------------------------------------------------------
  // THE VALUE SUB-TABLE (A5b, 2026-08-16). Lives INSIDE the existing props
  // tab: the eight-tab contract is untouched. It reads the served props_value
  // block and renders one of three honest states: value rows under the same
  // provisional treatment as the team slots, a priced-but-nothing-cleared
  // census, or the unarmed state naming BOTH environment variables the pull
  // is gated on, so an empty section always says which switch is off.
  var PROPS_MARKET_LABELS = {
    props_pitcher_strikeouts: "pitcher strikeouts",
    props_batter_total_bases: "batter total bases",
    props_batter_hits: "batter hits",
    props_batter_home_runs: "batter home runs"
  };

  function propsValueBlock() {
    var d = S.data || {};
    var pv = d.props_value || null;
    var out = ['<div class="bt-panel-sub" id="bt-props-value">Value against the books</div>'];
    if (!pv) {
      out.push(note("This payload predates the props_value block."));
      return out.join("");
    }
    var floor = pv.floor || {};
    var floorTxt = floorText({ min_edge: floor.min_edge,
                               provisional: floor.provisional === false ? false : true });
    var nPriced = (pv.rows || []).length || pv.n_rows || 0;
    if (!nPriced && !(pv.value_rows || []).length) {
      if (!pv.armed && pv.inert_reason) {
        out.push(note("<strong>No book prices to compare.</strong> " +
          esc(pv.inert_reason) + " The section spends nothing; the fair lines below " +
          "stand alone."));
      } else {
        out.push(note("No per-event props snapshot is cached for this slate. The pull " +
          "covers " + esc(String(pv.max_games_per_day)) + " game(s) a day: " +
          esc(pv.selection_rule || "") + "."));
      }
      return out.join("");
    }
    var rows = pv.value_rows || [];
    if (!rows.length) {
      out.push(note("<strong>" + pv.n_rows + " props side(s) priced and none " +
        "cleared " + floorTxt + ".</strong> Same floor as the team slots, never a " +
        "lower one invented to fill the table."));
      return out.join("");
    }
    out.push(note("Each row cleared " + floorTxt + " against a book price, the same " +
      "floor as the team slots. " + gl("Edge", "bet_edge") + " is model minus the " +
      "de-vigged fair from the minimum-hold book on the consensus line. Not advice."));
    out.push('<div class="bt-scroll mlbstats-scroll"><table class="bt-table mlbstats-table">' +
      '<thead><tr><th class="bt-l">Player</th><th class="bt-l">Market</th>' +
      "<th>Line</th><th class=\"bt-l\">Side</th><th>Price</th><th>Model</th>" +
      "<th>Fair</th><th>Edge</th><th>EV/u</th><th>&frac14; Kelly</th></tr></thead><tbody>" +
      rows.map(function (r) {
        var cls = r.edge == null ? "" : (r.edge > 0 ? " bt-pos" : " bt-neg");
        // The tag follows the floor, the same rule provBadge applies to the
        // team slots: a measured floor retires the word.
        return '<tr><td class="bt-l">' + esc(r.player || "") +
          (floor.provisional === false ? ""
            : ' <span class="bt-tag bt-tag-warn bt-prov">provisional</span>') + "</td>" +
          '<td class="bt-l">' + esc(PROPS_MARKET_LABELS[r.market] || r.market || "") +
          "</td><td>" + (r.line == null ? "-" : esc(String(r.line))) + "</td>" +
          '<td class="bt-l">' + esc(r.side || "") + "</td>" +
          "<td>" + fmtOdds(r.odds) + (r.book ? ' <span class="bt-dim">' +
            esc(r.book) + "</span>" : "") + "</td>" +
          "<td>" + pct(r.model_prob) + "</td>" +
          "<td>" + pct(r.market_fair_prob) + "</td>" +
          '<td class="' + cls + '">' + (r.edge == null ? "-"
            : signed(r.edge * 100, 1) + "%") + "</td>" +
          '<td class="' + cls + '">' + (r.ev_per_unit == null ? "-"
            : signed(r.ev_per_unit, 3)) + "</td>" +
          "<td>" + (r.kelly_quarter == null ? "-" : pct(r.kelly_quarter, 1)) +
          "</td></tr>";
      }).join("") + "</tbody></table></div>");
    if (r0Push(rows)) {
      out.push('<div class="bt-hold">' + r0Push(rows) + "</div>");
    }
    return out.join("");
  }

  // The first whole-number props line's push sentence, through the same
  // pushText the team board uses, so the two surfaces cannot phrase it apart.
  function r0Push(rows) {
    for (var i = 0; i < rows.length; i++) {
      var t = pushText(rows[i], "the Model column", "the EV/u column");
      if (t) return t;
    }
    return "";
  }

  function renderProps() {
    var d = S.data;
    if (!d) return empty("No props loaded", "The betting payload has not been built yet.");
    var pf = d.props_fair_lines || {};
    var head = note("<strong>Model fair lines, no book comparison.</strong> " +
      esc(pf.no_book_comparison_reason || ""));
    if (!(pf.pitchers || []).length && !(pf.hitters || []).length) {
      // The value block still renders: its unarmed state names the two
      // environment variables, and that answer holds on an empty slate too.
      // The reason is the payload's (props_fair_lines.empty_reason): an empty
      // props board on a priced slate is a corpus fact, not a missing slate.
      return head + empty("No props to price", pf.empty_reason || "No slate is loaded.") +
        '<div class="bt-panel">' + propsValueBlock() + "</div>";
    }
    var meth = pf.method || {};
    var out = [head];
    out.push('<div class="bt-panel"><div class="bt-panel-hd">Method</div><div class="bt-kv">' +
      kv("Pitchers", esc(meth.pitchers || "-")) +
      kv("Hitters", esc(meth.hitters || "-")) +
      kv("Lineups", esc(meth.lineup_assumption || "-")) +
      kv("Distribution", esc(meth.distribution || "-")) + "</div>" +
      propsValueBlock() + "</div>");

    out.push('<div class="bt-subhd">Starting pitchers</div>');
    out.push('<div class="bt-scroll mlbstats-scroll"><table class="bt-table mlbstats-table"><thead><tr><th class="bt-l">Pitcher</th><th>Opp</th>' +
      "<th>Exp IP</th><th>K fair</th><th>P(over)</th><th>ER fair</th><th>H fair</th></tr></thead><tbody>" +
      (pf.pitchers || []).map(function (p) {
        var k = propOf(p, "Strikeouts"), er = propOf(p, "Earned runs"), h = propOf(p, "Hits allowed");
        return '<tr><td class="bt-l">' + nameLink(p.mlbam, p.name) +
          ' <span class="bt-dim">' + esc(p.org || "") + "</span></td>" +
          "<td>" + esc(p.opp || "") + "</td><td>" + num(p.expected_ip, 1) + "</td>" +
          "<td>" + num(k.fair_line, 2) + "</td>" +
          "<td>" + (k.over_line != null ? "o" + k.over_line + " " + pct(k.p_over) : "-") + "</td>" +
          "<td>" + num(er.fair_line, 2) + "</td><td>" + num(h.fair_line, 2) + "</td></tr>";
      }).join("") + "</tbody></table></div>");

    out.push('<div class="bt-subhd">Hitters</div>');
    out.push('<div class="bt-scroll mlbstats-scroll"><table class="bt-table mlbstats-table"><thead><tr><th class="bt-l">Hitter</th><th>Slot</th>' +
      "<th>Exp PA</th><th>TB fair</th><th>P(TB 2+)</th><th>P(hit)</th><th>P(HR)</th></tr></thead><tbody>" +
      (pf.hitters || []).map(function (p) {
        var tb = propOf(p, "Total bases"), hh = propOf(p, "1+ hits"), hr = propOf(p, "1+ home runs");
        return '<tr><td class="bt-l">' + nameLink(p.mlbam, p.name) +
          ' <span class="bt-dim">' + esc(p.org || "") + "</span></td>" +
          "<td>" + (p.slot || "-") + "</td><td>" + num(p.expected_pa, 2) + "</td>" +
          "<td>" + num(tb.fair_line, 2) + "</td><td>" + pct(tb.p_over) + "</td>" +
          "<td>" + pct(hh.p_over) + "</td><td>" + pct(hr.p_over) + "</td></tr>";
      }).join("") + "</tbody></table></div>");
    return out.join("");
  }

  function propOf(rec, name) {
    var list = (rec && rec.props) || [];
    for (var i = 0; i < list.length; i++) if (list[i].prop === name) return list[i];
    return {};
  }

  // ---- section: parlays -----------------------------------------------------
  function renderParlays() {
    var d = S.data;
    var pc = (d && d.parlay_context) || { rules: [], legs: [] };
    var out = [];
    out.push('<div class="bt-panel"><div class="bt-panel-hd">Why there is no ' +
      gl("parlay", "parlay") + " of the day</div>" +
      "<p>" + esc(pc.featured_reason ||
        "A featured parlay needs a backtest that survives the correlation haircut.") + "</p>" +
      "<p>" + esc(pc.math_note || "") + "</p></div>");

    out.push('<div class="bt-subhd">Correlation rules</div>');
    out.push('<div class="bt-scroll mlbstats-scroll"><table class="bt-table mlbstats-table"><thead><tr><th class="bt-l">When</th><th class="bt-l">Why it matters</th>' +
      "<th>Builder</th></tr></thead><tbody>" +
      (pc.rules || []).map(function (r) {
        return '<tr><td class="bt-l">' + esc(r.when) + '</td><td class="bt-l">' + esc(r.why) +
          '</td><td><span class="bt-tag ' + (r.severity === "block" ? "bt-tag-block" : "bt-tag-warn") +
          '">' + esc(r.severity) + "</span></td></tr>";
      }).join("") + "</tbody></table></div>");

    out.push('<div class="bt-subhd">Builder</div>');
    if (!(pc.legs || []).length) {
      out.push(empty("No legs available", "No slate is priced. The Parlay calculator " +
        "under Calculators takes typed prices."));
    } else {
      out.push('<div class="bt-legpick"><select id="bt-legsel" class="bt-input">' +
        '<option value="">Add a leg...</option>' +
        (pc.legs || []).map(function (l, i) {
          return '<option value="' + i + '">' + esc(l.label) +
            (l.odds != null ? " (" + fmtOdds(l.odds) + ")" : "") +
            " &middot; model " + pct(l.model_prob) + "</option>";
        }).join("") + "</select></div>");
      out.push('<div id="bt-parlay-out"></div>');
    }
    return out.join("");
  }

  function wireParlay() {
    var sel = el("bt-legsel");
    if (!sel) return;
    sel.addEventListener("change", function () {
      var i = parseInt(sel.value, 10);
      var legs = ((S.data || {}).parlay_context || {}).legs || [];
      if (!isNaN(i) && legs[i]) S.legs.push(legs[i]);
      sel.value = "";
      paintParlay();
    });
    paintParlay();
  }

  function paintParlay() {
    var host = el("bt-parlay-out");
    if (!host) return;
    if (S.legs.length < 2) {
      host.innerHTML = empty(S.legs.length ? "One leg is not a parlay" : "No legs yet",
        "Add two or more legs.") +
        (S.legs.length ? legTable() : "");
      wireLegDrops(host);
      return;
    }
    var byGame = {}, blocked = false, warned = [];
    S.legs.forEach(function (l) {
      byGame[l.game_pk] = (byGame[l.game_pk] || 0) + 1;
    });
    Object.keys(byGame).forEach(function (g) {
      if (byGame[g] > 1) { blocked = true; warned.push(g); }
    });
    var pProd = S.legs.reduce(function (a, l) { return a * (l.model_prob || 0); }, 1);
    // A ticket has a price only if EVERY leg has one. With no odds feed the
    // legs carry model probabilities and a null price, and the old fold
    // substituted decimal 1.0 for the missing legs: that turned "no price" into
    // a confident EV of minus the miss probability, which is a number the page
    // has no business printing. Count the priced legs instead and refuse.
    var priced = 0, decProd = 1;
    S.legs.forEach(function (l) {
      var d = amToDec(l.odds);
      if (d) { priced++; decProd *= d; }
    });
    var allPriced = priced === S.legs.length;
    var body = legTable();
    if (blocked) {
      body += '<div class="bt-block"><strong>Same-game legs. The naive product is blocked.</strong> ' +
        "Legs from one game are correlated, so their product is not a price. Remove a leg, " +
        "or price the ticket as a same-game parlay at the book.</div>";
    } else if (!allPriced) {
      body += '<div class="bt-parlay-sum">' +
        chip("Legs", S.legs.length) +
        chip("Model probability", pct(pProd, 2)) + "</div>" +
        note("<strong>No price on this ticket.</strong> " + (S.legs.length - priced) + " of " +
          S.legs.length + " legs have no posted odds (no odds feed). A price, implied " +
          "probability and EV need a price on every leg. The Parlay calculator under " +
          "Calculators takes typed prices.");
    } else {
      body += '<div class="bt-parlay-sum">' +
        chip("Legs", S.legs.length) +
        chip("Model probability", pct(pProd, 2)) +
        chip("Parlay price", fmtOdds(decToAm(decProd))) +
        chip("Implied", pct(decToImplied(decProd), 2)) +
        chip("EV / unit", signed(evPerUnit(pProd, decProd), 3)) + "</div>" +
        note("Every leg is from a different game, so the legs are treated as independent.");
    }
    host.innerHTML = body;
    wireSortableTables(host);
    wireLegDrops(host);
  }

  function legTable() {
    var rows = S.legs.map(function (l, i) {
      return '<tr><td class="bt-l">' + esc(l.label) + "</td><td>" + pct(l.model_prob) +
        "</td><td>" + fmtOdds(l.odds) + '</td><td><button type="button" class="bt-btn bt-btn-x" ' +
        'data-legdrop="' + i + '">remove</button></td></tr>';
    }).join("");
    return '<div class="bt-scroll mlbstats-scroll"><table class="bt-table mlbstats-table"><thead><tr><th class="bt-l">Leg</th>' +
      "<th>Model</th><th>Price</th><th></th></tr></thead><tbody>" + rows +
      "</tbody></table></div>";
  }

  function wireLegDrops(host) {
    host.querySelectorAll("[data-legdrop]").forEach(function (b) {
      b.addEventListener("click", function () {
        S.legs.splice(parseInt(b.getAttribute("data-legdrop"), 10), 1);
        paintParlay();
      });
    });
  }

  // ---- section: calculators (pure client, no payload) -----------------------
  function renderCalc() {
    return [
      note("Browser-only arithmetic: no data file, odds feed or account needed."),
      calcBox("Odds converter", "bt-c1",
        field("American", "bt-c1-am", "-110") + field("Decimal", "bt-c1-dec", "1.909") +
        field("Implied %", "bt-c1-imp", "52.38"),
        "Type in any box; the others follow. Implied probability includes the vig."),
      calcBox("Vig and hold", "bt-c2",
        field("Side A (American)", "bt-c2-a", "-110") + field("Side B (American)", "bt-c2-b", "-110"),
        "Overround = sum of the implied probabilities. Hold = overround minus 100%, the " +
        "game cards' number. Book keeps = hold / overround, the share of a balanced handle " +
        "retained. Fair = proportional de-vig, as on the boards."),
      calcBox("Expected value", "bt-c3",
        field("Your probability %", "bt-c3-p", "55") + field("Price (American)", "bt-c3-odds", "-110") +
        field("Stake (units)", "bt-c3-stake", "1"),
        "Average return per unit staked, at your probability."),
      calcBox("Kelly", "bt-c4",
        field("Your probability %", "bt-c4-p", "55") + field("Price (American)", "bt-c4-odds", "-110"),
        "Informational only. The public record stakes a flat 1 unit so its ROI stays " +
        "auditable."),
      calcBox("Parlay", "bt-c5",
        field("Prices, comma separated", "bt-c5-legs", "-110, +150, -130") +
        field("Same game?", "bt-c5-same", "no"),
        "Same game = yes stops the product: correlated legs cannot be multiplied.")
    ].join("");
  }

  function calcBox(title, id, fields, why) {
    return '<div class="bt-calc" id="' + id + '"><div class="bt-calc-hd">' + esc(title) + "</div>" +
      '<div class="bt-calc-fields">' + fields + "</div>" +
      '<div class="bt-calc-out" id="' + id + '-out"></div>' +
      '<div class="bt-calc-why">' + esc(why) + "</div></div>";
  }
  function field(label, id, ph) {
    return '<label class="bt-field"><span>' + esc(label) + '</span>' +
      '<input class="bt-input" id="' + id + '" type="text" value="" placeholder="' + esc(ph) + '"></label>';
  }

  function wireCalc() {
    // 1. Converter. `guard` stops the three-way binding from fighting itself.
    var am = el("bt-c1-am"), dec = el("bt-c1-dec"), imp = el("bt-c1-imp"), guard = false;
    function conv(from) {
      if (guard || !am) return;
      guard = true;
      var d = null;
      if (from === "am") d = amToDec(am.value);
      else if (from === "dec") d = parseFloat(dec.value) || null;
      else { var p = parseFloat(imp.value); d = (p > 0 && p < 100) ? impliedToDec(p / 100) : null; }
      if (d && d > 1) {
        if (from !== "am") am.value = fmtOdds(decToAm(d));
        if (from !== "dec") dec.value = d.toFixed(4);
        if (from !== "imp") imp.value = (decToImplied(d) * 100).toFixed(2);
        el("bt-c1-out").innerHTML = chip("Decimal", d.toFixed(4)) +
          chip("American", fmtOdds(decToAm(d))) + chip("Implied", pct(decToImplied(d), 2)) +
          chip("Break-even win rate", pct(decToImplied(d), 2));
      } else {
        // The two boxes the reader is NOT typing in are cleared. Leaving the
        // last good conversion sitting next to an unparseable entry shows a
        // decimal and an implied percentage that belong to a price nobody
        // typed, which is worse than showing nothing.
        if (from !== "am") am.value = "";
        if (from !== "dec") dec.value = "";
        if (from !== "imp") imp.value = "";
        el("bt-c1-out").innerHTML = '<span class="bt-dim">Enter a price. American odds ' +
          "run from +100 and -100 outward.</span>";
      }
      guard = false;
    }
    if (am) { am.addEventListener("input", function () { conv("am"); }); }
    if (dec) { dec.addEventListener("input", function () { conv("dec"); }); }
    if (imp) { imp.addEventListener("input", function () { conv("imp"); }); }

    // 2. Vig / hold.
    function vig() {
      var a = amToDec(el("bt-c2-a").value), b = amToDec(el("bt-c2-b").value);
      var host = el("bt-c2-out");
      if (!a || !b) { host.innerHTML = '<span class="bt-dim">Enter both sides.</span>'; return; }
      var raw = decToImplied(a) + decToImplied(b);
      var fair = devig([a, b]);
      // "Hold" here is overround minus 100%, which is the definition
      // betting_model.hold_pct uses and the number the game cards publish, so
      // the two surfaces agree. It is NOT the share of a balanced handle the
      // book retains: that is the hold over the overround, and it is shown
      // beside it rather than left for the reader to assume they are the same.
      host.innerHTML = chip("Overround", (raw * 100).toFixed(2) + "%") +
        chip("Hold", ((raw - 1) * 100).toFixed(2) + "%") +
        chip("Book keeps", (100 * (raw - 1) / raw).toFixed(2) + "%") +
        chip("Fair A", pct(fair[0], 2)) + chip("Fair B", pct(fair[1], 2)) +
        chip("Fair A price", fmtOdds(decToAm(1 / fair[0]))) +
        chip("Fair B price", fmtOdds(decToAm(1 / fair[1])));
    }
    ["bt-c2-a", "bt-c2-b"].forEach(function (id) {
      var n = el(id); if (n) n.addEventListener("input", vig);
    });

    // 3. EV.
    function ev() {
      var p = parseFloat(el("bt-c3-p").value) / 100;
      var d = amToDec(el("bt-c3-odds").value);
      var st = parseFloat(el("bt-c3-stake").value);
      var host = el("bt-c3-out");
      if (!(p > 0 && p < 1) || !d) { host.innerHTML = '<span class="bt-dim">Enter a probability and a price.</span>'; return; }
      st = isFinite(st) && st > 0 ? st : 1;
      var e = evPerUnit(p, d);
      host.innerHTML = chip("EV per unit", signed(e, 4)) +
        chip("EV on " + st + "u", signed(e * st, 4)) +
        chip("Break-even probability", pct(decToImplied(d), 2)) +
        chip("Edge", signed((p - decToImplied(d)) * 100, 2) + "%");
    }
    ["bt-c3-p", "bt-c3-odds", "bt-c3-stake"].forEach(function (id) {
      var n = el(id); if (n) n.addEventListener("input", ev);
    });

    // 4. Kelly.
    function kel() {
      var p = parseFloat(el("bt-c4-p").value) / 100;
      var d = amToDec(el("bt-c4-odds").value);
      var host = el("bt-c4-out");
      if (!(p > 0 && p < 1) || !d) { host.innerHTML = '<span class="bt-dim">Enter a probability and a price.</span>'; return; }
      var f = kelly(p, d);
      host.innerHTML = chip("Full Kelly", pct(f, 2)) + chip("Half Kelly", pct(f / 2, 2)) +
        chip("Quarter Kelly", pct(f / 4, 2)) +
        chip("This site stakes", "1u flat");
    }
    ["bt-c4-p", "bt-c4-odds"].forEach(function (id) {
      var n = el(id); if (n) n.addEventListener("input", kel);
    });

    // 5. Parlay, with the same block the builder uses.
    function par() {
      var host = el("bt-c5-out");
      var same = String((el("bt-c5-same").value || "")).trim().toLowerCase();
      var parts = String(el("bt-c5-legs").value || "").split(",")
        .map(function (s) { return amToDec(s.trim()); }).filter(Boolean);
      if (parts.length < 2) { host.innerHTML = '<span class="bt-dim">Enter two or more prices.</span>'; return; }
      if (same === "y" || same === "yes" || same === "true") {
        host.innerHTML = '<div class="bt-block"><strong>Same-game parlay: no number.</strong> ' +
          "Legs from one game are correlated; the product of their prices is not the " +
          "ticket's price.</div>";
        return;
      }
      var d = parts.reduce(function (a, b) { return a * b; }, 1);
      host.innerHTML = chip("Legs", parts.length) + chip("Decimal", d.toFixed(4)) +
        chip("American", fmtOdds(decToAm(d))) + chip("Implied", pct(decToImplied(d), 2)) +
        chip("Break-even leg rate", pct(Math.pow(decToImplied(d), 1 / parts.length), 2));
    }
    ["bt-c5-legs", "bt-c5-same"].forEach(function (id) {
      var n = el(id); if (n) n.addEventListener("input", par);
    });

    // Seed every box from its placeholder so the page opens with worked numbers
    // rather than five empty forms.
    [["bt-c1-am", "-110"], ["bt-c2-a", "-110"], ["bt-c2-b", "-110"],
     ["bt-c3-p", "55"], ["bt-c3-odds", "-110"], ["bt-c3-stake", "1"],
     ["bt-c4-p", "55"], ["bt-c4-odds", "-110"],
     ["bt-c5-legs", "-110, +150, -130"], ["bt-c5-same", "no"]].forEach(function (pair) {
      var n = el(pair[0]); if (n && !n.value) n.value = pair[1];
    });
    conv("am"); vig(); ev(); kel(); par();
  }

  // ---- section: my bets -----------------------------------------------------
  // Server first when the account layer is configured and the reader is signed
  // in; localStorage otherwise. The two shapes are identical, so the renderer
  // never branches on where a row came from.
  function acct() { return window.EephusAccount || null; }
  function acctLive() {
    var a = acct();
    return !!(a && a.enabled && a.enabled() && a.isSignedIn && a.isSignedIn() && a.listBets);
  }
  function localBets() {
    try {
      var raw = JSON.parse(localStorage.getItem(LS_KEY) || "[]");
      return Array.isArray(raw) ? raw : [];
    } catch (e) { return []; }
  }
  function saveLocal(rows) {
    try { localStorage.setItem(LS_KEY, JSON.stringify(rows)); } catch (e) { /* private mode */ }
  }
  function loadBets() {
    if (!acctLive()) {
      S.bets = localBets(); S.betsSource = "local";
      return Promise.resolve(S.bets);
    }
    return acct().listBets().then(function (rows) {
      S.bets = Array.isArray(rows) ? rows : [];
      S.betsSource = "account";
      return S.bets;
    }).catch(function () {
      S.bets = localBets(); S.betsSource = "local";
      return S.bets;
    });
  }
  function addBet(row) {
    if (acctLive() && acct().addBet) {
      return acct().addBet(row).then(loadBets).catch(function () {
        var rows = localBets(); rows.push(row); saveLocal(rows);
        S.bets = rows; S.betsSource = "local";
      });
    }
    var rows = localBets();
    row.id = row.id || ("local-" + Date.now() + "-" + Math.floor(Math.random() * 1e6));
    rows.push(row); saveLocal(rows);
    S.bets = rows; S.betsSource = "local";
    return Promise.resolve(rows);
  }
  function updateBet(id, patch) {
    if (acctLive() && acct().updateBet) {
      return acct().updateBet(id, patch).then(loadBets).catch(function () { return loadBets(); });
    }
    var rows = localBets().map(function (r) {
      return r.id === id ? Object.assign({}, r, patch) : r;
    });
    saveLocal(rows); S.bets = rows;
    return Promise.resolve(rows);
  }
  // THE PUBLIC RECORD IS APPEND ONLY. This log is not the public record: it is
  // the reader's own, and a private log he cannot correct is a log he stops
  // using. Delete removes the row here and, when signed in, through the
  // account layer's deleteBet.
  function removeBet(id) {
    if (acctLive() && acct().deleteBet) {
      return acct().deleteBet(id).then(loadBets).catch(function () { return loadBets(); });
    }
    var rows = localBets().filter(function (r) { return r.id !== id; });
    saveLocal(rows); S.bets = rows;
    return Promise.resolve(rows);
  }
  // Merge-on-sign-in, cloning the watchlist adapter's contract. Never
  // destructive: it copies local rows up, it does not delete them.
  function mergeOnSignIn() {
    var a = acct();
    if (!acctLive() || !a.mergeLocalBets) return;
    var rows = localBets();
    if (!rows.length) return;
    a.mergeLocalBets(rows).then(function (res) {
      // Clear THIS module's store only once the server has the rows. The
      // account layer keys its own storage differently ("eephus.bets.v1" vs
      // this file's "eephus_bets_v1"), which is exactly how these rows used to
      // be orphaned on sign-in: the merge read the wrong store, inserted
      // nothing, and the view then switched to the account source with the
      // local rows still on disk and nothing left reading them.
      if (res && res.merged && !res.error) saveLocal([]);
      loadBets().then(paintBets);
    }).catch(function () { /* stay local; the rows are untouched */ });
  }

  function renderMyBets() {
    return '<div class="bt-panel"><div class="bt-panel-hd">My bets</div>' +
      "<p>Your log, separate from the public record. It works signed out (stored in this " +
      "browser) and syncs to your account once you sign in.</p>" +
      '<div id="bt-bet-form" class="bt-betform"></div></div>' +
      '<div id="bt-bets-out"></div>';
  }

  function wireBets() {
    var host = el("bt-bet-form");
    if (!host) return;
    host.innerHTML =
      field("Selection", "bt-b-sel", "Mets ML") +
      field("Market", "bt-b-mkt", "moneyline") +
      field("Price (American)", "bt-b-odds", "-140") +
      field("Stake (units)", "bt-b-stake", "1") +
      '<button type="button" class="bt-btn bt-btn-go" id="bt-b-add">Log the bet</button>';
    el("bt-b-add").addEventListener("click", function () {
      var sel = (el("bt-b-sel").value || "").trim();
      var odds = parseInt(el("bt-b-odds").value, 10);
      if (!sel || !isFinite(odds)) {
        var o = el("bt-bets-out");
        if (o) o.innerHTML = empty("Nothing logged", "A selection and a price are required.") + o.innerHTML;
        return;
      }
      addBet({
        sport: "MLB",
        market: (el("bt-b-mkt").value || "moneyline").trim(),
        selection: sel,
        odds: odds,
        stake: parseFloat(el("bt-b-stake").value) || 1,
        placed_at: new Date().toISOString(),
        settled_at: null,
        result: "open",
        payload: { source: "betting.js" }
      }).then(function () {
        el("bt-b-sel").value = "";
        paintBets();
      });
    });
    loadBets().then(paintBets);
    var a = acct();
    if (a && a.onAuthChange) a.onAuthChange(function () { mergeOnSignIn(); loadBets().then(paintBets); });
  }

  function paintBets() {
    var host = el("bt-bets-out");
    if (!host) return;
    var rows = S.bets || [];
    var src = S.betsSource === "account"
      ? "Synced to your account."
      : "Stored in this browser only. Sign in to keep them across devices.";
    if (!rows.length) {
      host.innerHTML = empty("No bets logged", src);
      return;
    }
    var w = 0, l = 0, units = 0, staked = 0;
    rows.forEach(function (r) {
      var d = amToDec(r.odds) || 1, st = Number(r.stake) || 1;
      if (r.result === "won") { w++; units += st * (d - 1); staked += st; }
      else if (r.result === "lost") { l++; units -= st; staked += st; }
    });
    var sum = '<div class="bt-parlay-sum">' + chip("Record", w + "-" + l) +
      chip("Net units", signed(units, 2)) +
      chip("ROI", staked ? signed(100 * units / staked, 2) + "%" : "-") +
      chip("Open", rows.filter(function (r) { return r.result === "open"; }).length) + "</div>";
    var body = '<div class="bt-scroll mlbstats-scroll"><table class="bt-table mlbstats-table"><thead><tr>' +
      '<th class="bt-l">Selection</th><th>Market</th>' +
      "<th>Price</th><th>Stake</th><th>Result</th><th></th></tr></thead><tbody>" +
      rows.map(function (r) {
        var cls = r.result === "won" ? " bt-pos" : (r.result === "lost" ? " bt-neg" : "");
        var id = esc(r.id);
        // A settled row keeps its controls. Grading was one click and a
        // misgrade used to be permanent: the buttons disappeared and there was
        // no delete either, so one slip left a wrong row in the log forever.
        var acts = (r.result === "open" || !r.result)
          ? '<button type="button" class="bt-btn" data-settle="won" data-id="' + id + '">won</button>' +
            '<button type="button" class="bt-btn" data-settle="lost" data-id="' + id + '">lost</button>' +
            '<button type="button" class="bt-btn" data-settle="void" data-id="' + id + '">void</button>'
          : '<button type="button" class="bt-btn" data-settle="open" data-id="' + id + '">reopen</button>';
        acts += '<button type="button" class="bt-btn bt-btn-x" data-betdrop="' + id + '">delete</button>';
        return '<tr><td class="bt-l">' + esc(r.selection) + "</td><td>" + esc(r.market || "") +
          "</td><td>" + fmtOdds(r.odds) + "</td><td>" + num(r.stake, 2) + "u</td>" +
          '<td class="' + cls + '">' + esc(r.result || "open") + "</td>" +
          '<td class="bt-acts">' + acts + "</td></tr>";
      }).join("") + "</tbody></table></div>";
    host.innerHTML = sum + body + note(esc(src));
    wireSortableTables(host);
    host.querySelectorAll("[data-settle]").forEach(function (b) {
      b.addEventListener("click", function () {
        var to = b.getAttribute("data-settle");
        updateBet(b.getAttribute("data-id"), {
          result: to,
          settled_at: to === "open" ? null : new Date().toISOString()
        }).then(paintBets);
      });
    });
    host.querySelectorAll("[data-betdrop]").forEach(function (b) {
      b.addEventListener("click", function () {
        removeBet(b.getAttribute("data-betdrop")).then(paintBets);
      });
    });
  }

  // ---- share card -----------------------------------------------------------
  function gfxChip() {
    if (!window.EEPHUS_GFX || !EEPHUS_GFX.chipHTML) return "";
    return EEPHUS_GFX.chipHTML("bt-gfx", "Generate GFX");
  }
  function wireGfx() {
    var b = el("bt-gfx");
    if (!b || !window.EEPHUS_GFX) return;
    b.addEventListener("click", function () {
      var bets = ((S.data || {}).team_bets) || [];
      EEPHUS_GFX.open({
        kind: "board", module: "betting", accentToken: "green",
        title: "MLB model board",
        subtitle: ((S.data || {}).slate_date || "") + " model probabilities, eephus.io",
        url: location.origin + "/betting/",
        filenameBase: "eephus-betting-" + ((S.data || {}).slate_date || "board"),
        caption: "Model probabilities only. 21+. Informational, not advice. 1-800-GAMBLER.",
        board: {
          columns: [
            { label: "Game", frac: 0.42, align: "left" },
            { label: "Away", frac: 0.16 }, { label: "Home", frac: 0.16 },
            { label: "Total", frac: 0.13 }, { label: "Park", frac: 0.13 }
          ],
          rows: bets.map(function (b2) {
            var m = b2.model || {};
            return { cells: [
              { t: b2.away.org + " at " + b2.home.org, sub: b2.venue || "" },
              { t: pct(m.p_away) }, { t: pct(m.p_home) },
              { t: num(m.fair_total, 2) }, { t: num(m.park_index, 2) }
            ] };
          }),
          counts: [10, 15, 30]
        }
      });
    });
  }

  function wireTeamView(root) {
    if (!root || !root.querySelectorAll) return;
    Array.prototype.forEach.call(root.querySelectorAll("[data-teamview]"), function (b) {
      b.addEventListener("click", function () {
        var v = b.getAttribute("data-teamview");
        if (!v || v === S.teamView) return;
        S.teamView = v;
        try { localStorage.setItem(TEAM_VIEW_KEY, v); } catch (e) { /* private mode */ }
        renderSection();
      });
    });
  }

  // ---- section plumbing -----------------------------------------------------
  function renderSection() {
    var root = el("betting-app-root");
    if (!root) return;
    var html;
    switch (S.section) {
      case "teams": html = renderTeam(); break;
      case "props": html = renderProps(); break;
      case "parlays": html = renderParlays(); break;
      case "calculators": html = renderCalc(); break;
      case "record": html = renderRecord(); break;
      case "validation": html = renderValidation(); break;
      case "futures": html = renderFutures(); break;
      case "mybets": html = renderMyBets(); break;
      default: html = renderPick();
    }
    if (S.error && S.section !== "calculators" && S.section !== "mybets") {
      html = pxState("failed", "<strong>The betting payload failed to load.</strong> " +
        esc(S.error) + ". The nightly build may be mid-run. " +
        '<button type="button" id="bt-retry" class="bt-btn">retry</button>', "bt-error") + html;
    }
    // The share chip rides the two board sections only; there is nothing to
    // share about a calculator.
    if (S.section === "teams" || S.section === "potd") html = '<div class="bt-toolbar">' + gfxChip() + "</div>" + html;
    root.innerHTML = html;
    var rb = el("bt-retry"); if (rb) rb.addEventListener("click", boot);
    if (S.section === "calculators") wireCalc();
    if (S.section === "mybets") wireBets();
    if (S.section === "parlays") wireParlay();
    if (S.section === "teams") wireTeamView(root);
    wireGfx();
    // Term spans get their tooltip + aria wiring here, after the section's
    // markup is in the DOM. wire() is idempotent and cheap on a container this
    // size, so it runs on every paint rather than only on the first.
    wireGl(root);
    // Every table in the section becomes sortable (owner ask 2026-09-05); the
    // wiring is idempotent per table, so a re-paint never double-binds.
    wireSortableTables(root);
  }

  // The shell ships the tabs, but the module injects any it is missing so a
  // shell/module version skew degrades to a working page rather than a tab
  // that cannot be reached.
  function ensureTabs() {
    var nav = document.querySelector(".mlbstats-sectionnav");
    if (!nav) return;
    SECTIONS.forEach(function (id) {
      if (nav.querySelector('[data-bettingsection="' + id + '"]')) return;
      var b = document.createElement("button");
      b.type = "button";
      b.className = "mlbstats-sectionbtn";
      b.setAttribute("data-bettingsection", id);
      b.setAttribute("role", "tab");
      b.setAttribute("aria-selected", "false");
      b.textContent = SECTION_LABELS[id] || id;
      nav.appendChild(b);
    });
  }
  function syncTabs() {
    // The potd tab's copy follows the served frame (the 2026-08-16 ruling):
    // "Model Watch" while the gates are closed, "Pick of the Day" when the
    // payload says they opened. Rewritten on every paint so a shell-shipped
    // button flips too.
    var potdLabel = watchMode() ? "Model Watch" : "Pick of the Day";
    document.querySelectorAll(".mlbstats-sectionbtn[data-bettingsection]").forEach(function (b) {
      var id = b.getAttribute("data-bettingsection");
      if (id === "potd" && b.textContent !== potdLabel) b.textContent = potdLabel;
      var on = id === S.section;
      b.classList.toggle("active", on);
      b.setAttribute("aria-selected", on ? "true" : "false");
    });
  }
  function wireTabs() {
    document.querySelectorAll(".mlbstats-sectionbtn[data-bettingsection]").forEach(function (b) {
      if (b.getAttribute("data-btwired")) return;
      b.setAttribute("data-btwired", "1");
      b.addEventListener("click", function () {
        S.section = b.getAttribute("data-bettingsection");
        syncTabs(); renderSection(); writeHash();
      });
    });
  }

  // ---- hash router ----------------------------------------------------------
  // #section=potd|teams|props|parlays|calculators|record|validation|mybets,
  // the eight ids in SECTIONS. The alternation is baked into the regex rather
  // than looked up in a map, so "#section=constructor" cannot resolve off
  // Object.prototype (the fantasy.js lesson).
  function hashParam(h, key, pat) {
    var m = new RegExp("(?:^#|[#&])" + key + "=(" + pat + ")(?:&|$)").exec(h || "");
    return m ? m[1] : null;
  }
  // Returns TRUE when the hash it just read was canonical. An invalid section
  // was already refused by the alternation above, so the page rendered the
  // default - but the ADDRESS BAR kept the bad value until the reader happened
  // to click a tab, so a shared link named a section that does not exist and
  // the page disagreed with its own URL. The callers rewrite on a false.
  function readHash() {
    var h = location.hash || "";
    var s = hashParam(h, "section", SECTION_PAT);
    if (s) S.section = s;
    return !(!s && /(?:^#|[#&])section=/.test(h));
  }
  function writeHash() {
    LAST_HASH = "#section=" + S.section;
    try { history.replaceState(null, "", LAST_HASH); } catch (e) { /* optional nicety */ }
  }
  window.addEventListener("hashchange", function () {
    if ((location.hash || "") === LAST_HASH) return;
    if (!readHash()) writeHash();
    syncTabs(); renderSection();
  });

  // ---- boot -----------------------------------------------------------------
  function paintAll() {
    renderLegal(); renderBanner();
    ensureTabs(); wireTabs(); syncTabs(); renderSection();
  }

  // Which payload URL the last boot() actually fetched. The entitlement
  // callback compares it against dataUrl() NOW: a difference means the answer
  // to "who is this reader" changed after the fetch went out, and the page is
  // painted off the wrong file until it re-fetches.
  var LOADED_URL = null;
  function boot() {
    // The legal block goes up FIRST, before any fetch can fail, so it is on
    // screen even if nothing else ever arrives.
    if (!readHash()) writeHash();
    renderLegal();
    // Then the lamp loader, in the section root below the legal block, until
    // the payload settles and paintAll() replaces it.
    var lr = el("betting-app-root");
    if (lr) lr.innerHTML = pxState("loading", esc("Loading the betting board..."));
    var url = dataUrl();
    LOADED_URL = url;
    fetch(url, { cache: "no-cache" }).then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    }).then(function (d) {
      S.data = d || null;
      S.error = (d && d.n_games != null) ? null : "the payload arrived empty";
      paintAll();
      if (!LINKS && window.EEPHUS_HUB && EEPHUS_HUB.links) {
        EEPHUS_HUB.links().then(function (L) { LINKS = L || null; renderSection(); });
      }
    }).catch(function (e) {
      S.data = null;
      S.error = String((e && e.message) || e);
      paintAll();
    });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
  // THE MEMBER-FIRST-PAINT FIX (2026-08-16). Entitlement resolves after boot:
  // the account layer is deferred and its session read is async, so the boot
  // fetch necessarily goes out on a guess. When the resolved answer changes
  // which payload this reader should see (preview vs full, either direction),
  // re-run boot against the correct URL. When it does not, nothing happens,
  // so with gating off this whole seam is inert.
  (function () {
    var D = window.EephusDiamond;
    if (D && D.onEntitlement) D.onEntitlement(function () {
      if (LOADED_URL !== null && dataUrl() !== LOADED_URL) boot();
    });
  })();

  // ---- styles ---------------------------------------------------------------
  // Injected here rather than in a separate stylesheet, matching the fantasy.js
  // house pattern: the module owns its own look and the shell stays CSS-file
  // free. Every colour is a theme token with a fallback; no literal hex is used
  // for anything a theme should control.
  var css = document.createElement("style");
  css.textContent = [
    ".bt-legal{display:flex;gap:10px;align-items:flex-start;border:1px solid var(--accent-gold,#a80);border-radius:0;padding:10px 12px;margin:10px 0;background:var(--bg-secondary)}",
    ".bt-legal-badge{font:700 13px/1 var(--font-retro,monospace);color:var(--text-primary);border:2px solid var(--accent-gold,#a80);padding:5px 7px;white-space:nowrap}",
    ".bt-legal-body p{margin:0 0 4px;font-size:12.5px;color:var(--text-secondary)}",
    ".bt-legal-help{font-weight:700;color:var(--text-primary)}",
    ".bt-asof{font-size:12px;color:var(--text-tertiary);margin:4px 0}",
    ".bt-stale{border-left:3px solid var(--accent-gold,#a80);padding:6px 10px;margin:6px 0;font-size:12.5px;color:var(--text-primary)}",
    ".bt-pick.bt-pick-past{border-color:var(--accent-gold,#a80)}",
    ".bt-chip{font:600 10px/1 var(--font-retro,monospace);border:1px solid var(--border,#333);padding:3px 6px;margin-left:4px;text-transform:uppercase;letter-spacing:.03em}",
    ".bt-chip-ok{color:var(--accent-green,#3a9);border-color:var(--accent-green,#3a9)}",
    ".bt-chip-warn{color:var(--text-primary);border-color:var(--accent-gold,#a80);border-width:1.5px}",
    ".bt-chip-stage{color:var(--accent-lilac,#a8f);border-color:var(--accent-lilac,#a8f)}",
    ".bt-toolbar{display:flex;justify-content:flex-end;margin:6px 0}",
    ".bt-subhd{font:700 12px/1 var(--font-retro,monospace);color:var(--text-tertiary);text-transform:uppercase;letter-spacing:.05em;margin:16px 0 6px}",
    ".bt-panel{border:1px solid var(--border,#333);background:var(--bg-secondary);padding:12px;margin:10px 0}",
    ".bt-panel-hd{font:700 13px/1.2 var(--font-retro,monospace);color:var(--text-primary);margin-bottom:8px}",
    ".bt-panel-sub{font:700 11px/1 var(--font-retro,monospace);color:var(--text-tertiary);text-transform:uppercase;margin:12px 0 6px}",
    ".bt-panel p{font-size:12.5px;color:var(--text-secondary);margin:0 0 8px}",
    ".bt-list{margin:0 0 8px 18px;padding:0;font-size:12.5px;color:var(--text-secondary)}",
    ".bt-kv{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:4px 14px;margin:6px 0}",
    ".bt-kv-row{display:flex;justify-content:space-between;gap:10px;font-size:12px;border-bottom:1px solid var(--border-light,#222);padding:3px 0}",
    ".bt-kv-k{color:var(--text-tertiary)}.bt-kv-v{color:var(--text-primary);font-weight:600;text-align:right}",
    // Wide content scrolls inside its own box. Without this the six-column
    // backtest table pushed the whole document sideways on a narrow phone,
    // which drags every other element off-screen with it.
    ".bt-scroll{max-width:100%;overflow-x:auto;-webkit-overflow-scrolling:touch}",
    // THE SHARED DIALECT, PLUS THE TWO THINGS IT ASSUMES THAT ARE NOT TRUE
    // HERE. Every table on this page now also carries .mlbstats-scroll /
    // .mlbstats-table so it inherits the site-wide sticky header and frozen
    // identity column out of assets/site.css. Two of those rules were written
    // for the /mlbstats/ boards and need correcting for this page:
    //
    //   1. The frozen cell fills with --bg-primary, because on /mlbstats/ the
    //      table sits on the page background. Every table here sits inside a
    //      .bt-panel or .bt-game on --bg-secondary, so an unpatched freeze
    //      paints a page-coloured stripe down the left of each panel. The two
    //      rules below repeat site.css's selector with one extra class, which
    //      out-specifies it (0,5,1 against 0,4,1) rather than racing it in the
    //      cascade.
    //   2. .mlbstats-table sets white-space:nowrap on every cell. The gate
    //      table's "what it needs" cell is a PARAGRAPH, so it keeps its own
    //      wrap - see the .bt-gate-need note further down, which now carries
    //      the table class to win that specificity fight.
    ".bt-scroll.mlbstats-scroll:has(> .mlbstats-table) .bt-table td:first-child:not([colspan])" +
      "{background:var(--bg-secondary)}",
    ".bt-scroll.mlbstats-scroll:has(> .mlbstats-table) .bt-table thead th:first-child" +
      "{background:var(--bg-secondary)}",
    ".bt-table{width:100%;border-collapse:collapse;font-size:12.5px;margin:6px 0}",
    ".bt-acts{white-space:nowrap}",
    ".bt-table th{text-align:right;font:600 10px/1 var(--font-retro,monospace);color:var(--text-tertiary);text-transform:uppercase;letter-spacing:.03em;padding:6px 8px;border-bottom:1px solid var(--border,#333)}",
    ".bt-table td{text-align:right;padding:6px 8px;border-bottom:1px solid var(--border-light,#222);color:var(--text-primary)}",
    ".bt-table th.bt-l,.bt-table td.bt-l{text-align:left}",
    ".bt-table th.bt-sortable{cursor:pointer;user-select:none}",
    ".bt-table th.bt-sortable:focus-visible{outline:2px solid var(--accent-cyan,#2a7);outline-offset:-2px}",
    ".bt-table th.is-sorted{color:var(--text-primary);border-bottom:2px solid var(--accent-gold,#a80)}",
    ".bt-table th[aria-sort=\"ascending\"]::after{content:' \\25B2';font-size:8px}",
    ".bt-table th[aria-sort=\"descending\"]::after{content:' \\25BC';font-size:8px}",
    ".bt-pos{color:var(--accent-green,#3a9)}.bt-neg{color:var(--accent-red,#c55)}",
    ".bt-dim{color:var(--text-tertiary)}",
    ".bt-note{font-size:12px;color:var(--text-secondary);background:var(--bg-secondary);border-left:3px solid var(--accent-cyan,#2a7);padding:8px 10px;margin:8px 0}",
    ".bt-error{border:1px solid var(--accent-red,#c55);padding:12px;margin:8px 0;color:var(--text-primary);background:var(--bg-secondary);font-size:12.5px}",
    ".bt-nopick{border:1px solid var(--accent-gold,#a80);padding:14px;margin:10px 0;background:var(--bg-secondary)}",
    ".bt-nopick-hd{font:700 14px/1 var(--font-retro,monospace);color:var(--text-primary);margin-bottom:8px;text-transform:uppercase;letter-spacing:.05em}",
    ".bt-nopick p{font-size:12.5px;color:var(--text-secondary);margin:0 0 6px}",
    ".bt-pick{border:1px solid var(--accent-green,#3a9);padding:14px;margin:10px 0;background:var(--bg-secondary)}",
    ".bt-pick-hd{font:700 11px/1 var(--font-retro,monospace);color:var(--accent-green,#3a9);text-transform:uppercase;letter-spacing:.06em;display:flex;align-items:center;gap:8px;flex-wrap:wrap}",
    ".bt-pick-sel{font:700 20px/1.2 var(--font-retro,monospace);color:var(--text-primary);margin:6px 0}",
    ".bt-pick-meta{font-size:12px;color:var(--text-tertiary);margin-bottom:8px}",
    ".bt-pick p{font-size:12.5px;color:var(--text-secondary);margin:0 0 8px}",
    ".bt-pick-lead{color:var(--text-tertiary)}",
    // An empty slot must not read as a failed load. It keeps the card frame and
    // the heading, and loses only the accent that says "here is a pick".
    ".bt-pick-empty{border-color:var(--border,#333)}",
    ".bt-pick-empty .bt-pick-hd{color:var(--text-tertiary)}",
    ".bt-pick-empty .px-state{margin:10px 0 0}",
    ".bt-pick-empty .px-state p{margin:6px 0 0}",
    ".bt-pick-redacted{border-color:var(--accent-lilac,#a8f)}",
    ".bt-pick-redacted .bt-pick-hd{color:var(--accent-lilac,#a8f)}",
    ".bt-numchip-info{border-style:dashed}",
    // The collapsed accounting. The summary is a control, so it reads as one.
    ".bt-details{border:1px solid var(--border,#333);background:var(--bg-secondary);margin:10px 0}",
    ".bt-details-sum{font:700 12px/1.3 var(--font-retro,monospace);color:var(--text-primary);padding:10px 12px;cursor:pointer;list-style:none}",
    ".bt-details-sum::-webkit-details-marker{display:none}",
    ".bt-details-sum::before{content:'+ ';color:var(--accent-cyan,#2a7)}",
    ".bt-details[open] .bt-details-sum::before{content:'- '}",
    ".bt-details-sum:hover{color:var(--accent-cyan,#2a7)}",
    ".bt-details-body{padding:0 12px 4px}",
    ".bt-details-body .bt-panel{border:0;padding:0;margin:0 0 12px}",
    ".bt-bestval{margin-left:6px;white-space:nowrap}",
    ".bt-table tr.bt-bestrow td{background:var(--bg-hover,var(--bg-secondary))}",
    // The frozen identity cell is painted by the two rules above at a higher
    // specificity than the highlight, so without this the badged row lights up
    // everywhere except the column carrying the badge.
    ".bt-scroll.mlbstats-scroll:has(> .mlbstats-table) .bt-table tr.bt-bestrow " +
      "td:first-child{background:var(--bg-hover,var(--bg-secondary))}",
    ".bt-numchip{display:inline-flex;flex-direction:column;border:1px solid var(--border,#333);padding:4px 8px;margin:0 6px 6px 0;min-width:82px}",
    ".bt-numchip-l{font:600 9px/1 var(--font-retro,monospace);color:var(--text-tertiary);text-transform:uppercase;letter-spacing:.04em}",
    ".bt-numchip-v{font:700 14px/1.2 var(--font-retro,monospace);color:var(--text-primary);margin-top:3px}",
    ".bt-game{border:1px solid var(--border,#333);background:var(--bg-secondary);padding:10px 12px;margin:10px 0}",
    ".bt-game-hd{display:flex;justify-content:space-between;align-items:baseline;flex-wrap:wrap;gap:8px}",
    ".bt-game-teams{font:700 14px/1.2 var(--font-retro,monospace);color:var(--text-primary);display:flex;align-items:center;gap:6px}",
    ".bt-at{color:var(--text-tertiary);font-weight:400}",
    ".bt-game-sub{font-size:11.5px;color:var(--text-tertiary)}",
    ".bt-game-probs{margin:8px 0 4px}",
    ".bt-game-sp{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:4px 12px;margin-bottom:6px}",
    ".bt-sp{display:flex;gap:8px;align-items:baseline;font-size:12px;border-bottom:1px solid var(--border-light,#222);padding:3px 0}",
    ".bt-sp-org{font:700 10px/1 var(--font-retro,monospace);color:var(--text-tertiary);min-width:34px}",
    ".bt-sp-name{flex:1;min-width:0;color:var(--text-primary);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}",
    ".bt-sp-num{font:600 10px/1 var(--font-retro,monospace);color:var(--text-tertiary)}",
    ".bt-markets{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:0 16px}",
    ".bt-market-table{margin:0}",
    ".bt-market-hd{font:700 10px/1 var(--font-retro,monospace);color:var(--text-tertiary);text-transform:uppercase;margin-top:6px}",
    ".bt-faironly{font-size:12px;color:var(--text-secondary);padding:6px 0}",
    ".bt-hold{font-size:11px;color:var(--text-tertiary);margin-top:6px}",
    // The Team Bets view toggle (owner ask 2026-09-07). Every colour is a theme
    // token so the control follows light and dark with the rest of the module.
    ".bt-seg{display:flex;gap:0;margin:10px 0;border:1px solid var(--border,#333);width:max-content}",
    ".bt-seg-btn{font:600 11px/1 var(--font-retro,monospace);text-transform:uppercase;"
      + "letter-spacing:.04em;padding:7px 13px;background:var(--bg-secondary);"
      + "color:var(--text-secondary);border:0;cursor:pointer}",
    ".bt-seg-btn + .bt-seg-btn{border-left:1px solid var(--border,#333)}",
    ".bt-seg-btn:hover{background:var(--bg-tertiary);color:var(--text-primary)}",
    ".bt-seg-btn.is-on{background:var(--accent-cyan,#2aa);color:var(--bg-primary)}",
    ".bt-seg-btn:focus-visible{outline:2px solid var(--accent-cyan,#2aa);outline-offset:-2px}",
    // A leg that clears the served floor is tinted, not recoloured: the text
    // must keep its own contrast, so this is a background wash only.
    ".bt-table tbody tr.bt-row-value td{background:color-mix(in srgb,var(--accent-green,#3a9) 9%,transparent)}",
    ".bt-table tbody tr.bt-row-value.bt-row-plain td{background:color-mix(in srgb,var(--text-secondary,#888) 8%,transparent)}",
    ".bt-tag{font:700 9px/1 var(--font-retro,monospace);padding:3px 5px;text-transform:uppercase}",
    ".bt-tag-warn{color:var(--text-primary);border:1.5px solid var(--accent-gold,#a80)}",
    ".bt-tag-ok{color:var(--accent-green,#3a9);border:1.5px solid var(--accent-green,#3a9)}",
    ".bt-tag-plain{color:var(--text-secondary);border:1.5px solid var(--border-light,var(--border,#888))}",
    // The provisional badge's own hook, dead until 2026-08-16: provBadge has
    // emitted .bt-prov since the labelling contract landed and no rule in this
    // sheet ever matched it. Dashed is this sheet's dialect for informational,
    // not validated (.bt-numchip-info), on the gold .bt-tag-warn already sets.
    ".bt-prov{border-style:dashed;white-space:nowrap}",
    // The watch card's two additions (2026-08-16): the slot rule's own settled
    // record, and the collapsible worked de-vig. Both are body copy, not
    // chrome, so they take the secondary text tokens and a thin gold rail that
    // matches the provisional dialect.
    ".bt-tagrec{border-left:3px solid var(--accent-gold,#a80);padding:6px 10px;margin:8px 0;font-size:12.5px;color:var(--text-secondary)}",
    ".bt-tagrec strong{color:var(--text-primary)}",
    ".bt-devigex{border:1px solid var(--border,#333);margin:8px 0;background:var(--bg-secondary)}",
    ".bt-devigex-sum{cursor:pointer;padding:7px 10px;font-size:12.5px;color:var(--text-primary)}",
    ".bt-devigex-body{padding:2px 10px 8px;font-size:12.5px;color:var(--text-secondary)}",
    ".bt-devigex-body ul{margin:4px 0}",
    // The gate table's `why` is a paragraph, not a cell value. Without a cap
    // it stretches the row to its own length and the whole table becomes a
    // horizontal scroll of one sentence. Both selectors are qualified by
    // .bt-table so they out-specify .mlbstats-table td's nowrap (0,2,1 against
    // 0,1,1); unqualified they lost it the moment the shared class went on.
    ".bt-table td.bt-gate-need{max-width:46ch;white-space:normal}",
    ".bt-table .bt-gate-why{font-size:11.5px;color:var(--text-tertiary);margin-top:3px;white-space:normal}",
    ".bt-gate-more{margin-top:3px}",
    ".bt-gate-more > summary{display:none}",
    ".bt-gate-more > summary::-webkit-details-marker{display:none}",
    ".bt-tag-block{color:var(--text-on-accent,#fff);background:var(--accent-red,#c55)}",
    ".bt-block{border:1px solid var(--accent-red,#c55);padding:10px;margin:8px 0;font-size:12.5px;color:var(--text-secondary);background:var(--bg-secondary)}",
    ".bt-block strong{color:var(--text-primary);display:block;margin-bottom:4px}",
    ".bt-parlay-sum{margin:8px 0}",
    ".bt-legpick{margin:8px 0}",
    ".bt-calc{border:1px solid var(--border,#333);background:var(--bg-secondary);padding:12px;margin:10px 0}",
    ".bt-calc-hd{font:700 13px/1 var(--font-retro,monospace);color:var(--text-primary);margin-bottom:8px}",
    ".bt-calc-fields,.bt-betform{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:8px;align-items:end}",
    ".bt-field{display:flex;flex-direction:column;gap:3px;font:600 10px/1 var(--font-retro,monospace);color:var(--text-tertiary);text-transform:uppercase;letter-spacing:.03em}",
    ".bt-input{font:600 13px/1 var(--font-retro,monospace);padding:7px 9px;border:1px solid var(--border,#3a3a3a);background:var(--bg-primary,transparent);color:var(--text-primary);border-radius:0;width:100%;box-sizing:border-box}",
    ".bt-calc-out{margin:10px 0 6px;min-height:22px}",
    ".bt-calc-why{font-size:11.5px;color:var(--text-tertiary)}",
    ".bt-btn{font:600 11px/1 var(--font-retro,monospace);padding:6px 10px;border:1px solid var(--border,#3a3a3a);background:var(--bg-secondary);color:var(--text-secondary);cursor:pointer;border-radius:0;margin-left:4px;" +
      "transition:background-color 120ms ease,color 120ms ease,border-color 120ms ease}",
    // --transition-hover IS NOT DEFINED ON THIS PAGE. The token lives in
    // prospx/index.html's inline :root block and nowhere else - it is not in
    // assets/site.css - so on /betting/ this var() always fell through to its
    // `none` fallback and the hover transition never once ran. The declaration
    // is written out here, matching the token's own value, rather than left as
    // a reference to something the page cannot resolve. It sits on the base
    // rule, not on :hover, so the colour eases back out as well as in.
    ".bt-btn:hover{background:var(--bg-hover,var(--bg-secondary))}",
    // Conversion chips (stage + preview slice) are anchors, so they need the
    // chip's own colour rather than the global link colour.
    ".bt-chip-link{text-decoration:none;cursor:pointer}",
    ".bt-chip-link:hover{text-decoration:underline}",
    ".bt-btn-go{background:var(--accent-cyan,#2a7);color:var(--text-on-accent,#fff);border-color:transparent;margin-left:0}",
    ".bt-btn-x{color:var(--accent-red,#c55)}",
    ".bt-link{color:var(--accent-cyan,#2a7);text-decoration:none}.bt-link:hover{text-decoration:underline}",
    // ---- the feed-health strip ---------------------------------------------
    // It sits above the tabs and it is the first thing on the page after the
    // legal card, so it is a rule and not a card: one line, monospace, and a
    // gold left edge when the close half has never run.
    ".bt-fh{margin:8px 0 4px;border-left:3px solid var(--border,#333);background:var(--bg-secondary);padding:6px 10px}",
    ".bt-fh-red{border-left-color:var(--accent-gold,#a80)}",
    ".bt-fh-line{display:flex;flex-wrap:wrap;align-items:baseline;gap:4px 14px;font:600 11px/1.5 var(--font-retro-mono,var(--font-retro,monospace))}",
    ".bt-fh-hd{color:var(--text-tertiary);letter-spacing:.08em}",
    ".bt-fh-seg{display:inline-flex;gap:5px;align-items:baseline;white-space:nowrap}",
    ".bt-fh-k{color:var(--text-tertiary);text-transform:uppercase;letter-spacing:.04em}",
    ".bt-fh-v{color:var(--text-primary)}",
    ".bt-fh-warn .bt-fh-v{color:var(--text-primary);border-bottom:1.5px solid var(--accent-gold,#a80)}",
    ".bt-fh-note{color:var(--text-secondary);font-weight:400;white-space:normal;flex:1 1 100%}",
    // ---- the validation tab ------------------------------------------------
    ".bt-headline{border:2px solid var(--accent-gold,#a80);background:var(--bg-secondary);padding:14px;margin:10px 0}",
    ".bt-headline-hd{font:700 15px/1.25 var(--font-retro,monospace);color:var(--text-primary);text-transform:uppercase;letter-spacing:.03em;margin-bottom:8px}",
    ".bt-headline p{font-size:12.5px;color:var(--text-secondary);margin:0 0 8px}",
    ".bt-clocks{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:12px;margin-top:8px}",
    ".bt-clock{border:1px solid var(--border,#333);padding:10px 12px;background:var(--bg-primary,transparent)}",
    ".bt-clock-hd{font:700 12px/1 var(--font-retro,monospace);color:var(--text-primary);text-transform:uppercase;letter-spacing:.04em}",
    ".bt-clock-q{font-size:11.5px;color:var(--text-tertiary);margin:4px 0 8px}",
    ".bt-clock-n{font:700 26px/1 var(--font-retro,monospace);color:var(--text-primary)}",
    ".bt-clock-need{font-size:13px;color:var(--text-tertiary);font-weight:400}",
    ".bt-clock-fine{font-size:11px;color:var(--text-tertiary);margin-top:4px}",
    ".bt-meter{margin:8px 0 2px;max-width:280px}",
    ".bt-meter-fill{display:block;height:100%;background:var(--accent-cyan,#2a7)}",
    ".bt-bar{display:inline-block;height:9px;min-width:1px;background:var(--accent-cyan,#2a7)}",
    // ---- the inline SVG charts (A6) ----------------------------------------
    // Tokens only, through classes, in the page's own dialect: cyan is the
    // one data series, green/red is the polarity pair the tables already use,
    // gold is the reference the reader must not miss, and grid/axis text wear
    // the recessive tokens. Marks are 2px lines and 8px dots.
    ".bt-chart{margin:8px 0}",
    ".bt-svg{display:block;max-width:100%;height:auto}",
    ".bt-svg-rel,.bt-svg-trend{max-width:360px}",
    ".bt-svg-roi{max-width:420px}",
    ".bt-svg-line{stroke:var(--accent-cyan,#2a7);stroke-width:2;fill:none;stroke-linejoin:round}",
    ".bt-svg-dot{fill:var(--accent-cyan,#2a7);stroke:var(--bg-secondary,#111);stroke-width:2}",
    ".bt-svg-ref{stroke:var(--text-tertiary,#888);stroke-width:1;stroke-dasharray:4 3}",
    ".bt-svg-goldref{stroke:var(--accent-gold,#a80);stroke-width:1.5;stroke-dasharray:5 3}",
    ".bt-svg-grid{stroke:var(--border-light,#222);stroke-width:1}",
    ".bt-svg-axis{fill:var(--text-tertiary,#888);font:600 9px var(--font-retro,monospace)}",
    ".bt-svg-track{fill:var(--bg-primary,transparent);stroke:var(--border,#333)}",
    ".bt-svg-fill{fill:var(--accent-cyan,#2a7)}",
    ".bt-svg-pos{fill:var(--accent-green,#3a9)}",
    ".bt-svg-neg{fill:var(--accent-red,#c55)}",
    ".bt-cell-meter .bt-svg{max-width:130px;display:inline-block;vertical-align:middle}",
    ".bt-sha{font:600 10px/1 var(--font-retro-mono,var(--font-retro,monospace));color:var(--text-secondary);word-break:break-all}",
    ".bt-unpriced{white-space:normal}",
    // ---- Dugout context (In-Game Management) ------------------------------
    // Site tokens only. Never --accent-green, --accent-red, --up, --down, a vt-*
    // ruler class, .bt-pos, .bt-neg, .bt-tag-ok or .bt-tag-warn: nothing in the
    // block may read as a signal beside a price. Dark mode needs nothing extra.
    ".bt-dugout{border-top:1px dashed var(--border-light,#222);margin-top:8px;padding-top:4px}",
    ".bt-dugout-sum{font:700 11px/1.3 var(--font-retro,monospace);color:var(--text-tertiary);text-transform:uppercase;letter-spacing:.05em;padding:6px 0}",
    ".bt-dugout-body{padding:4px 2px 6px;font-size:12px;color:var(--text-secondary)}",
    ".bt-dugout-np{color:var(--text-primary);margin:4px 0 8px}",
    ".bt-dugout-clubs{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:8px 14px}",
    ".bt-dugout-club{min-width:0}",
    ".bt-dugout-org{font:700 12px/1.2 var(--font-retro,monospace);color:var(--text-primary);display:flex;align-items:center;gap:6px;margin-bottom:4px}",
    ".bt-dugout-hd{font:600 9px/1 var(--font-retro,monospace);color:var(--text-tertiary);text-transform:uppercase;letter-spacing:.04em;margin:8px 0 3px}",
    ".bt-dugout-zs{display:flex;flex-wrap:wrap;gap:4px 8px}",
    ".bt-dugout-z{display:inline-flex;flex-direction:column;border:1px solid var(--border,#333);padding:3px 7px;min-width:64px}",
    ".bt-dugout-zl{font:600 9px/1 var(--font-retro,monospace);color:var(--text-tertiary)}",
    ".bt-dugout-zv{font:700 13px/1.2 var(--font-retro,monospace);color:var(--text-primary);margin-top:2px}",
    ".bt-dugout-t{width:100%;border-collapse:collapse;font-size:12px}",
    ".bt-dugout-t td,.bt-dugout-t th{padding:3px 6px;border-bottom:1px solid var(--border-light,#222);text-align:right;color:var(--text-primary)}",
    ".bt-dugout-t th{font:600 9px/1 var(--font-retro,monospace);color:var(--text-tertiary);text-transform:uppercase}",
    ".bt-dugout-t td.bt-l,.bt-dugout-t th.bt-l{text-align:left}",
    ".bt-dugout-fine{font-size:11.5px;color:var(--text-tertiary);margin:6px 0 0}",
    ".bt-dugout-src{font-size:11px;color:var(--text-tertiary);margin-top:6px}",
    ".bt-dugout-link{display:inline-block;margin-top:6px;font-size:12px}",
    ".bt-dugout-dark{border-left-color:var(--border,#333)}",
    // ---- <= 640px ----------------------------------------------------------
    // A SEPARATE TIER, ADDED BELOW THE 720px RULE RATHER THAN REPLACING IT, so
    // nothing between 641 and 720 moves. Everything here is about a 390px
    // viewport: the feed strip wraps to two lines instead of scrolling the
    // document sideways, the two clocks stack, and the gate table's need/why
    // paragraph collapses into a disclosure so a five-column table fits.
    "@media (max-width:720px){.bt-markets{grid-template-columns:minmax(0,1fr)}.bt-table{font-size:12px}.bt-table th,.bt-table td{padding:5px 4px}}",
    "@media (max-width:640px){",
    ".bt-fh-line{gap:2px 12px;font-size:10.5px}",
    ".bt-fh-hd{flex:1 1 100%}",
    ".bt-fh-seg{white-space:normal}",
    ".bt-clocks{grid-template-columns:minmax(0,1fr)}",
    ".bt-clock-n{font-size:22px}",
    ".bt-headline-hd{font-size:13.5px}",
    ".bt-kv{grid-template-columns:minmax(0,1fr)}",
    ".bt-table td.bt-gate-need{max-width:24ch}",
    ".bt-gate-more > summary{display:list-item;list-style:none}",
    ".bt-gate-sum{font:600 10px/1.3 var(--font-retro,monospace);color:var(--accent-cyan,#2a7);cursor:pointer;text-transform:uppercase;letter-spacing:.04em;padding:3px 0}",
    ".bt-pick-sel{font-size:17px}",
    ".bt-dugout-body{padding:6px 8px}",
    ".bt-dugout-link{display:block;margin-top:6px}",
    "}"
  ].join("");
  document.head.appendChild(css);
})();
