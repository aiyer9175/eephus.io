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
  var SECTIONS = ["potd", "teams", "props", "parlays", "calculators", "record", "mybets"];
  var SECTION_PAT = SECTIONS.join("|");
  var SECTION_LABELS = {
    potd: "Pick of the Day", teams: "Team Bets", props: "Player Props",
    parlays: "Parlays", calculators: "Calculators", record: "The Record",
    mybets: "My Bets"
  };

  var S = { data: null, section: "potd", error: null, legs: [], bets: [], betsSource: "local" };
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
    staking: "Every pick on the public record is a flat 1 unit. Kelly is shown as information, never as a stake."
  };

  // ---- the Diamond gate, wired and OFF -------------------------------------
  // assets/diamond-config.js (owned by the diamond-core lane) sets
  // window.EEPHUS_DIAMOND = { gating: false, ... }. While gating is off, and
  // while the file is absent entirely, every reader gets the full payload;
  // this preview build is fully public by owner decision. The seam exists now
  // so that flipping the flag later is a config change rather than a rewrite:
  // a non-member would then read the preview slice betting_export already
  // writes. Genuinely gated data cannot live in /data/ on a static site, so
  // the honest paywall is a Supabase-served path, not this.
  function diamondCfg() { return window.EEPHUS_DIAMOND || {}; }
  function gatingOn() { return !!diamondCfg().gating; }
  function isDiamond() {
    var a = window.EephusAccount;
    try { return !!(a && a.isDiamond && a.isDiamond()); } catch (e) { return false; }
  }
  function gated() { return gatingOn() && !isDiamond(); }
  function dataUrl() { return gated() ? PREVIEW_URL : DATA_URL; }

  // ---- helpers --------------------------------------------------------------
  function el(id) { return document.getElementById(id); }
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
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
  // rendered container. A slug the artifact does not carry renders a term that
  // looks clickable and defines nothing, which is worse than plain text, so
  // every slug used on this page was checked against the artifact first.
  //
  // WHAT IS DELIBERATELY NOT WRAPPED. The betting vocabulary proper - edge,
  // vig, hold, overround, de-vig, closing line value, unit, EV per unit, Kelly,
  // fair line, moneyline, runline, total - has NO entry in data/glossary.json
  // today. Those words are left as plain text rather than pointed at a
  // near-miss slug: a tooltip that defines the wrong thing on a page about
  // money is a worse failure than no tooltip. Add the entries in
  // build_glossary_data.py and the spans can follow in one pass.
  function gl(label, slug) {
    return '<span class="g-term" data-gl="' + esc(slug) + '">' + esc(label) + "</span>";
  }
  function wireGl(node) {
    try { if (node && window.EEPHUS_GL && EEPHUS_GL.wire) EEPHUS_GL.wire(node); }
    catch (e) { /* the glossary is enrichment; the page works without it */ }
  }
  function note(text) { return '<div class="bt-note">' + text + "</div>"; }
  function empty(title, why) {
    return '<div class="bt-empty"><strong>' + esc(title) + "</strong>" +
      (why ? "<span>" + esc(why) + "</span>" : "") + "</div>";
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
  function evPerUnit(p, dec) { return p * (dec - 1) - (1 - p); }
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
  // The one sentence the pick section leads with. Built from the gate the
  // reader can actually count, so it reads "600 needed, 0 today" rather than
  // "the model is unvalidated" with no way to check the claim.
  function noPickHeadline(v) {
    if (!v) return "No pick: this payload carries no validation state, so treat the model " +
      "as unvalidated.";
    if (v.available === false) {
      return "No pick: " + (v.reason || "the validation state is unknown") + ".";
    }
    var g = gateById(v, "vintage_sample");
    if (g) {
      return "No pick: the model is unvalidated until " + g.need + " exist, and " +
        haveText(g) + " exist today.";
    }
    return "No pick: the model is unvalidated and no minimum edge has been measured.";
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
        "<p>No. This payload carries no validation state, which means it was built before " +
        "the vintage grading lane existed. Treat every number on this page as unvalidated.</p></div>";
    }
    if (v.available === false) {
      return '<div class="bt-panel">' + rows.join("") + "<p><strong>No.</strong> " +
        esc(sentence(v.reason) || "The validation state is unknown.") + "</p></div>";
    }
    var vin = v.vintage || {}, cov = v.coverage || {}, gate = v.gate || {};
    var need = vin.min_graded_games_for_min_edge;

    rows.push("<p><strong>" + (v.validated ? "Yes." : "No.") + "</strong> " +
      (v.validated
        ? "The vintage mode has cleared every gate below, and the headline numbers on this " +
          "page come from it."
        : "The headline numbers on this page come from the <strong>" +
          esc(v.headline_mode || "contaminated") + "</strong> mode, which cannot validate " +
          "anything. " + esc((v.mode_meaning || {}).contaminated || "")) + "</p>");

    if ((v.mode_meaning || {}).vintage) {
      rows.push("<p><strong>The honest mode.</strong> " + esc(v.mode_meaning.vintage) + " " +
        "It has graded " + (vin.n_graded == null ? "-" : vin.n_graded) + " of the " +
        (v.n_games_completed == null ? "-" : v.n_games_completed) + " completed games in the " +
        "cache, and skipped " + (vin.n_skipped_no_vintage == null ? "-" : vin.n_skipped_no_vintage) +
        " for want of a snapshot dated before them.</p>");
    }

    rows.push('<div class="bt-kv">' +
      kv("Dated leaderboard snapshots", cov.n_vintages == null ? "-" : cov.n_vintages) +
      kv("Snapshot range", cov.first ? esc(cov.first) + " to " + esc(cov.last) : "none yet") +
      kv("Missing days inside that range", (cov.missing_dates || []).length) +
      kv("First game date a snapshot can price",
         cov.earliest_gradable_game_date ? esc(cov.earliest_gradable_game_date) : "-") +
      kv("Games graded by the honest mode", vin.n_graded == null ? "-" : vin.n_graded) +
      kv("Graded games needed for a threshold", need == null ? "-" : need) +
      "</div>");

    if ((gate.gates || []).length) {
      rows.push('<div class="bt-panel-sub">The three gates on a published pick</div>');
      rows.push('<div class="bt-scroll mlbstats-scroll"><table class="bt-table mlbstats-table"><thead><tr>' +
        '<th class="bt-l">Gate</th><th class="bt-l">What it needs</th><th>Have</th>' +
        "<th>State</th></tr></thead><tbody>" +
        gate.gates.map(function (g) {
          return '<tr><td class="bt-l">' + esc(g.id) + "</td>" +
            '<td class="bt-l bt-gate-need">' + esc(g.need || "") +
            (g.why ? '<div class="bt-gate-why">' + esc(g.why) + "</div>" : "") + "</td>" +
            "<td>" + esc(haveText(g)) + "</td>" +
            '<td><span class="bt-tag ' + (g.open ? "bt-tag-ok" : "bt-tag-warn") + '">' +
            (g.open ? "open" : "closed") + "</span></td></tr>";
        }).join("") + "</tbody></table></div>");
      rows.push(note(esc(gate.n_open + " of " + gate.n_gates + " gates are open. ") +
        esc(gate.policy || "")));
    }

    rows.push('<div class="bt-panel-sub">When does that change</div>');
    rows.push("<p>One dated snapshot lands per night, and a completed game becomes gradable " +
      "only once a snapshot predates it. So the honest sample starts at games played on or " +
      "after " + (cov.earliest_gradable_game_date ? esc(cov.earliest_gradable_game_date) :
        "the first night the snapshot runs") + ", and it grows by roughly a slate a day from " +
      "there until it reaches " + (need == null ? "the threshold" : need) + ". " +
      "There is no projected date on this page, because turning a game count into a calendar " +
      "date needs a games-per-night rate this module does not measure, and a made-up date is " +
      "the same sin as a made-up edge.</p>");
    if (v.generated_at) {
      rows.push('<div class="bt-asof">Backtest artifact generated ' + esc(v.generated_at) +
        (v.model_version ? " &middot; " + esc(v.model_version) : "") + "</div>");
    }
    return '<div class="bt-panel">' + rows.join("") + "</div>";
  }

  // ---- model banner ---------------------------------------------------------
  function renderBanner() {
    var host = el("betting-banner");
    if (!host) return;
    if (!S.data) {
      host.innerHTML = '<div class="bt-asof">Model payload not loaded. The calculators and ' +
        "your bet tracker below still work.</div>";
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
      'title="What Diamond is, and what it costs when it opens">' +
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
    chips.push('<span class="bt-chip ' + (st.odds_feed === "ok" ? "bt-chip-ok" : "bt-chip-warn") + '">' +
      (st.odds_feed === "ok" ? "odds feed live" : "no odds feed") + "</span>");
    if (gated()) {
      chips.push('<a class="bt-chip bt-chip-warn bt-chip-link" href="/diamond/">preview slice</a>');
    }
    host.innerHTML = '<div class="bt-asof">' +
      esc(S.data.slate_date || "") + " slate &middot; " + (S.data.n_games || 0) +
      " games priced &middot; " + chips.join(" ") + "</div>";
    wireGl(host);
  }

  // ---- section: pick of the day ---------------------------------------------
  function renderPick() {
    var d = S.data;
    var out = [];
    if (!d) {
      return empty("Pick of the day is unavailable",
        "The betting payload has not been built yet. Check back after the next build.");
    }
    var p = d.pick_of_the_day;
    if (!p) {
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
      out.push('<div class="bt-nopick"><div class="bt-nopick-hd">No pick today</div>' +
        "<p>" + esc(noPickHeadline(vstate())) + "</p>" + lines +
        "<p>A pick ships when two things are true: an odds feed is live, and the vintage " +
        "mode has measured a minimum edge worth betting on games it could not see. Neither " +
        "is true yet, so there is nothing here. That is the honest state, not a bug.</p></div>");
    } else {
      out.push('<div class="bt-pick">' +
        '<div class="bt-pick-hd">Pick of the day</div>' +
        '<div class="bt-pick-sel">' + esc(p.label || p.side || "") + " " + fmtOdds(p.odds) + "</div>" +
        '<div class="bt-pick-meta">' + esc(p.matchup || "") + " &middot; " + esc(p.book || "") +
        " &middot; stake " + num(p.stake_units, 1) + "u</div>" +
        '<div class="bt-pick-nums">' +
        chip("Model", pct(p.model_prob)) + chip("Market fair", pct(p.market_fair_prob)) +
        chip("Edge", signed(p.edge * 100, 1) + "%") + chip("EV / unit", signed(p.ev_per_unit, 3)) +
        "</div></div>");
    }
    out.push(validationPanel());
    out.push(modelPanel(d.model || {}));
    return out.join("");
  }

  // ---- section: the record --------------------------------------------------
  function renderRecord() {
    var d = S.data;
    return recordPanel(d ? d.record : null) + validationPanel() +
      '<div class="bt-panel"><div class="bt-panel-hd">How a pick gets graded</div>' +
      "<p>Every published pick carries the timestamp, the book, the price at post " +
      "and a flat one unit. It settles won, lost or void, and it is then graded a " +
      "second time against the closing line.</p>" +
      "<p>Closing line value is the honest test. Beating the close means the market " +
      "moved toward the pick after it was posted, which is evidence the pick had " +
      "information in it. Winning a bet is not evidence of anything on its own, and " +
      "one season of results is a smaller sample than it feels like.</p>" +
      "<p>Two CLV numbers get published side by side: price CLV, the posted decimal " +
      "over the closing decimal minus one, and probability CLV, the implied " +
      "probability at close minus at post. Beat-close rate is the plain yes or no " +
      "across every graded pick.</p></div>";
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
    if (!sk || sk.t == null) {
      return "Each contaminated block beats both baselines on the point estimate, which is " +
        "a point estimate and not a significance test.";
    }
    var head = "Each contaminated block beats both baselines on the point estimate. On the " +
      "forward split that margin over the home-field baseline is " + signed(sk.delta, 6) +
      " Brier at t = " + num(sk.t, 2) + ", which ";
    if (sk.beats_baseline_95) {
      return head + "clears the one-sided 95% bar of 1.645.";
    }
    return head + "does NOT clear the one-sided 95% bar of 1.645: a margin that size needs " +
      "about " + (sk.n_for_95 == null ? "more" : sk.n_for_95) + " games and the split has " +
      (fwd.n == null ? "fewer" : fwd.n) + ". Treat it as not significant.";
  }

  function modelPanel(m) {
    var bt = m.backtest || {};
    var rows = [];
    rows.push('<div class="bt-panel-hd">How the number is made</div>');
    rows.push("<p>Game probabilities come from the same measurements the rest of the site " +
      "runs on: team " + gl("Offense+", "offense_plus") + " (the " + gl("HEM+", "hem_plus") +
      " rollup), team " + gl("Bullpen+", "bullpen_plus") + " (" + gl("REM+", "rem_plus") +
      "), the listed starter's own " + gl("SEM+", "sem_plus") + " for the innings a starter " +
      "covers, the park run index, and home field. Expected runs go into a Poisson difference " +
      "for the margin, which gives the moneyline, the runline and the fair total together.</p>");
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
      rows.push(note("Lower Brier is better. " + skillSentence(blocks) +
        " None of that validates the model: the team inputs in the contaminated rows are " +
        "season to date, so every graded game sits inside its own features. " +
        esc(bt.note || "")));
    }
    if (m.known_limits && m.known_limits.length) {
      rows.push('<div class="bt-panel-sub">What it does not know</div><ul class="bt-list">' +
        m.known_limits.map(function (x) { return "<li>" + esc(x) + "</li>"; }).join("") + "</ul>");
    }
    return '<div class="bt-panel">' + rows.join("") + "</div>";
  }

  function kv(k, v) {
    return '<div class="bt-kv-row"><span class="bt-kv-k">' + esc(k) +
      '</span><span class="bt-kv-v">' + v + "</span></div>";
  }

  function recordPanel(r) {
    var body;
    if (!r || !r.n_rows) {
      body = empty("The record starts when the picks do",
        "No pick has been published, so there is nothing to grade. When picks start, every " +
        "one of them lands here with the book, the price at post, a flat 1 unit stake, and " +
        "the closing line it is graded against. Rows are never edited or deleted.");
    } else {
      body = '<div class="bt-kv">' +
        kv("Record", r.won + "-" + r.lost + (r.push ? "-" + r.push : "")) +
        kv("Net units", signed(r.net_units, 2)) +
        kv("ROI", r.roi_pct == null ? "-" : signed(r.roi_pct, 2) + "%") +
        kv("Beat close", r.beat_close_rate == null ? "not graded yet" : pct(r.beat_close_rate)) +
        kv("Average CLV", r.avg_clv_pct == null ? "not graded yet" : signed(r.avg_clv_pct, 2) + "%") +
        kv("Open", r.n_open) +
        "</div>";
    }
    var url = (S.data && S.data.record_url) || "/data/betting_record.json";
    return '<div class="bt-panel"><div class="bt-panel-hd">The public record</div>' + body +
      "<p>" + esc((S.data && S.data.record_policy) ||
        "Append only. Rows are never edited or deleted; a correction is a new row.") + " " +
      'The raw file is <a class="bt-link" href="' + esc(url) + '">' + esc(url) + "</a>.</p></div>";
  }

  // ---- section: team bets ---------------------------------------------------
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
    var head = hasMarket ? "" : note("No odds feed is configured, so these are model fair " +
      "prices with nothing to compare them against." +
      (reason ? " The build reports: " + esc(reason) + "." : ""));
    return head + bets.map(gameCard).join("");
  }

  function gameCard(b) {
    var m = b.model || {};
    var hd = '<div class="bt-game-hd">' +
      '<div class="bt-game-teams">' + teamLogo(b.away.org) + " " + esc(b.away.org) +
      ' <span class="bt-at">at</span> ' + teamLogo(b.home.org) + " " + esc(b.home.org) + "</div>" +
      '<div class="bt-game-sub">' + esc(b.venue || "") +
      (b.start ? " &middot; " + esc(String(b.start).slice(11, 16)) + " UTC" : "") + "</div></div>";

    var probs = '<div class="bt-game-probs">' +
      chip(esc(b.away.org), pct(m.p_away)) + chip(esc(b.home.org), pct(m.p_home)) +
      chip("Fair total", num(m.fair_total, 2)) +
      chip("Park", num(m.park_index, 2)) + "</div>";

    var sp = '<div class="bt-game-sp">' +
      spLine(b.away, m.away_prevention) + spLine(b.home, m.home_prevention) + "</div>";

    var blocks = [marketBlock("Moneyline", b.moneyline)];
    if (b.runline) blocks.push(marketBlock("Runline", b.runline));
    if (b.total && b.total.sides) blocks.push(marketBlock("Total " + b.total.line, b.total.sides));
    else blocks.push('<div class="bt-market"><div class="bt-market-hd">Total</div>' +
      '<div class="bt-faironly">Model fair total ' + num(m.fair_total, 2) +
      ". No posted line to compare.</div></div>");

    var hold = "";
    if (b.market && (b.market.moneyline_hold_pct != null || b.market.total_hold_pct != null)) {
      hold = '<div class="bt-hold">Book hold: moneyline ' +
        num(b.market.moneyline_hold_pct, 2) + "%, total " + num(b.market.total_hold_pct, 2) +
        "%. Fair probabilities de-vigged by the proportional method.</div>";
    }
    return '<div class="bt-game">' + hd + probs + sp +
      '<div class="bt-markets">' + blocks.join("") + "</div>" + hold + "</div>";
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

  function marketBlock(title, rows) {
    if (!rows || !rows.length) return "";
    var hasBook = rows.some(function (r) { return r.odds != null; });
    var head = "<tr><th class=\"bt-l\">" + esc(title) + "</th><th>Model</th>" +
      (hasBook ? "<th>Price</th><th>Fair</th><th>Edge</th><th>EV/u</th><th>Kelly</th>" :
        "<th>Fair price</th>") + "</tr>";
    var body = rows.map(function (r) {
      var cells = "<td class=\"bt-l\">" + esc(r.label || r.side) + "</td>" +
        "<td>" + pct(r.model_prob) + "</td>";
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
      return "<tr>" + cells + "</tr>";
    }).join("");
    return '<div class="bt-market"><div class="bt-scroll mlbstats-scroll"><table class="bt-table bt-market-table mlbstats-table">' +
      "<thead>" + head + "</thead><tbody>" + body + "</tbody></table></div></div>";
  }

  // ---- section: props -------------------------------------------------------
  function renderProps() {
    var d = S.data;
    if (!d) return empty("No props loaded", "The betting payload has not been built yet.");
    var pf = d.props_fair_lines || {};
    var head = note("<strong>Model fair lines, no book comparison.</strong> " +
      esc(pf.no_book_comparison_reason || ""));
    if (!(pf.pitchers || []).length && !(pf.hitters || []).length) {
      return head + empty("No props to price", "No slate is loaded.");
    }
    var meth = pf.method || {};
    var out = [head];
    out.push('<div class="bt-panel"><div class="bt-panel-hd">Method</div><div class="bt-kv">' +
      kv("Pitchers", esc(meth.pitchers || "-")) +
      kv("Hitters", esc(meth.hitters || "-")) +
      kv("Lineups", esc(meth.lineup_assumption || "-")) +
      kv("Distribution", esc(meth.distribution || "-")) + "</div></div>");

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
    out.push('<div class="bt-panel"><div class="bt-panel-hd">Why there is no parlay of the day</div>' +
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
      out.push(empty("No legs available", "No slate is priced, so there is nothing to chain. " +
        "The parlay calculator under Calculators takes hand-entered odds and works with no data."));
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
        "Add two or more legs to see the parlay math.") +
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
        "Two legs from one game are not independent, so multiplying them is not a price. " +
        "This builder will not print a number it cannot stand behind. Remove a leg, or treat " +
        "the ticket as a same-game parlay and price it at the book.</div>";
    } else if (!allPriced) {
      body += '<div class="bt-parlay-sum">' +
        chip("Legs", S.legs.length) +
        chip("Model probability", pct(pProd, 2)) + "</div>" +
        note("<strong>No price on this ticket.</strong> " + (S.legs.length - priced) + " of " +
          S.legs.length + " legs have no posted odds, because no odds feed is configured. " +
          "The model probability above is ours and stands on its own. A parlay price, an " +
          "implied probability and an EV all need a real price on every leg, so none of them " +
          "is shown. The parlay calculator under Calculators takes prices you type in.");
    } else {
      body += '<div class="bt-parlay-sum">' +
        chip("Legs", S.legs.length) +
        chip("Model probability", pct(pProd, 2)) +
        chip("Parlay price", fmtOdds(decToAm(decProd))) +
        chip("Implied", pct(decToImplied(decProd), 2)) +
        chip("EV / unit", signed(evPerUnit(pProd, decProd), 3)) + "</div>" +
        note("Independent legs only. Every leg above is from a different game, so the product " +
          "is arithmetic rather than an assumption.");
    }
    host.innerHTML = body;
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
      note("These calculators are pure arithmetic in your browser. They need no data file, " +
        "no odds feed and no account, and they keep working when everything else on this " +
        "page is empty."),
      calcBox("Odds converter", "bt-c1",
        field("American", "bt-c1-am", "-110") + field("Decimal", "bt-c1-dec", "1.909") +
        field("Implied %", "bt-c1-imp", "52.38"),
        "Type in any one box. The other two follow. Implied probability includes the vig."),
      calcBox("Vig and hold", "bt-c2",
        field("Side A (American)", "bt-c2-a", "-110") + field("Side B (American)", "bt-c2-b", "-110"),
        "Overround is the two implied prices added up. Hold is that figure over 100%, the " +
        "same number the game cards publish. Book keeps is the share of a balanced handle " +
        "the book actually retains, which is the hold divided by the overround: at -110 " +
        "both ways the hold reads 4.76% and the book keeps 4.55% of what is staked. Fair " +
        "probabilities are de-vigged proportionally, the same method the boards use."),
      calcBox("Expected value", "bt-c3",
        field("Your probability %", "bt-c3-p", "55") + field("Price (American)", "bt-c3-odds", "-110") +
        field("Stake (units)", "bt-c3-stake", "1"),
        "EV is what the bet returns on average per unit staked, at your probability."),
      calcBox("Kelly", "bt-c4",
        field("Your probability %", "bt-c4-p", "55") + field("Price (American)", "bt-c4-odds", "-110"),
        "Kelly is informational on this site. Every pick on the public record is a flat " +
        "1 unit, because a variable stake makes a published ROI impossible to audit."),
      calcBox("Parlay", "bt-c5",
        field("Prices, comma separated", "bt-c5-legs", "-110, +150, -130") +
        field("Same game?", "bt-c5-same", "no"),
        "Answer yes to Same game and the multiplication stops. Correlated legs cannot be " +
        "multiplied, and a builder that pretends otherwise is selling you a worse number " +
        "than the book already did.")
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
        el("bt-c1-out").innerHTML = '<span class="bt-dim">Enter a price. American runs ' +
          "from +100 and -100 outward; there is nothing between them.</span>";
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
          "Legs from one game are correlated, so the product of the prices is not the price " +
          "of the ticket. Price a same-game parlay at the book and compare it to nothing here.</div>";
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
    a.mergeLocalBets(rows).then(function () { loadBets().then(paintBets); })
      .catch(function () { /* stay local */ });
  }

  function renderMyBets() {
    return '<div class="bt-panel"><div class="bt-panel-hd">My bets</div>' +
      "<p>Your own log, separate from the site's public record. It works signed out: rows " +
      "live in this browser until you sign in, and sync to your account after that.</p>" +
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
      case "mybets": html = renderMyBets(); break;
      default: html = renderPick();
    }
    if (S.error && S.section !== "calculators" && S.section !== "mybets") {
      html = '<div class="bt-error" role="alert"><strong>The betting payload failed to load.</strong> ' +
        esc(S.error) + ' The nightly build may be mid-run. ' +
        '<button type="button" id="bt-retry" class="bt-btn">retry</button></div>' + html;
    }
    // The share chip rides the two board sections only; there is nothing to
    // share about a calculator.
    if (S.section === "teams" || S.section === "potd") html = '<div class="bt-toolbar">' + gfxChip() + "</div>" + html;
    root.innerHTML = html;
    var rb = el("bt-retry"); if (rb) rb.addEventListener("click", boot);
    if (S.section === "calculators") wireCalc();
    if (S.section === "mybets") wireBets();
    if (S.section === "parlays") wireParlay();
    wireGfx();
    // Term spans get their tooltip + aria wiring here, after the section's
    // markup is in the DOM. wire() is idempotent and cheap on a container this
    // size, so it runs on every paint rather than only on the first.
    wireGl(root);
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
    document.querySelectorAll(".mlbstats-sectionbtn[data-bettingsection]").forEach(function (b) {
      var on = b.getAttribute("data-bettingsection") === S.section;
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
  // #section=pick|team|props|parlays|calc|mybets. The alternation is baked into
  // the regex rather than looked up in a map, so "#section=constructor" cannot
  // resolve off Object.prototype (the fantasy.js lesson).
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

  function boot() {
    // The legal block goes up FIRST, before any fetch can fail, so it is on
    // screen even if nothing else ever arrives.
    if (!readHash()) writeHash();
    renderLegal();
    fetch(dataUrl(), { cache: "no-cache" }).then(function (r) {
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
    ".bt-pos{color:var(--accent-green,#3a9)}.bt-neg{color:var(--accent-red,#c55)}",
    ".bt-dim{color:var(--text-tertiary)}",
    ".bt-note{font-size:12px;color:var(--text-secondary);background:var(--bg-secondary);border-left:3px solid var(--accent-cyan,#2a7);padding:8px 10px;margin:8px 0}",
    ".bt-empty{display:flex;flex-direction:column;gap:4px;border:1px dashed var(--border,#333);padding:14px;margin:10px 0;color:var(--text-secondary);font-size:12.5px}",
    ".bt-empty strong{color:var(--text-primary);font-size:13px}",
    ".bt-error{border:1px solid var(--accent-red,#c55);padding:12px;margin:8px 0;color:var(--text-primary);background:var(--bg-secondary);font-size:12.5px}",
    ".bt-nopick{border:1px solid var(--accent-gold,#a80);padding:14px;margin:10px 0;background:var(--bg-secondary)}",
    ".bt-nopick-hd{font:700 14px/1 var(--font-retro,monospace);color:var(--text-primary);margin-bottom:8px;text-transform:uppercase;letter-spacing:.05em}",
    ".bt-nopick p{font-size:12.5px;color:var(--text-secondary);margin:0 0 6px}",
    ".bt-pick{border:1px solid var(--accent-green,#3a9);padding:14px;margin:10px 0;background:var(--bg-secondary)}",
    ".bt-pick-hd{font:700 11px/1 var(--font-retro,monospace);color:var(--accent-green,#3a9);text-transform:uppercase;letter-spacing:.06em}",
    ".bt-pick-sel{font:700 20px/1.2 var(--font-retro,monospace);color:var(--text-primary);margin:6px 0}",
    ".bt-pick-meta{font-size:12px;color:var(--text-tertiary);margin-bottom:8px}",
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
    ".bt-tag{font:700 9px/1 var(--font-retro,monospace);padding:3px 5px;text-transform:uppercase}",
    ".bt-tag-warn{color:var(--text-primary);border:1.5px solid var(--accent-gold,#a80)}",
    ".bt-tag-ok{color:var(--accent-green,#3a9);border:1.5px solid var(--accent-green,#3a9)}",
    // The gate table's `why` is a paragraph, not a cell value. Without a cap
    // it stretches the row to its own length and the whole table becomes a
    // horizontal scroll of one sentence. Both selectors are qualified by
    // .bt-table so they out-specify .mlbstats-table td's nowrap (0,2,1 against
    // 0,1,1); unqualified they lost it the moment the shared class went on.
    ".bt-table td.bt-gate-need{max-width:46ch;white-space:normal}",
    ".bt-table .bt-gate-why{font-size:11.5px;color:var(--text-tertiary);margin-top:3px;white-space:normal}",
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
    ".bt-btn{font:600 11px/1 var(--font-retro,monospace);padding:6px 10px;border:1px solid var(--border,#3a3a3a);background:var(--bg-secondary);color:var(--text-secondary);cursor:pointer;border-radius:0;margin-left:4px}",
    // --transition-hover IS NOT DEFINED ON THIS PAGE. The token lives in
    // prospx/index.html's inline :root block and nowhere else - it is not in
    // assets/site.css - so on /betting/ this var() always fell through to its
    // `none` fallback and the hover transition never once ran. The declaration
    // is written out here, matching the token's own value, rather than left as
    // a reference to something the page cannot resolve.
    ".bt-btn:hover{background:var(--bg-hover,var(--bg-secondary));" +
      "transition:background-color 120ms ease,color 120ms ease,border-color 120ms ease}",
    // Conversion chips (stage + preview slice) are anchors, so they need the
    // chip's own colour rather than the global link colour.
    ".bt-chip-link{text-decoration:none;cursor:pointer}",
    ".bt-chip-link:hover{text-decoration:underline}",
    ".bt-btn-go{background:var(--accent-cyan,#2a7);color:var(--text-on-accent,#fff);border-color:transparent;margin-left:0}",
    ".bt-btn-x{color:var(--accent-red,#c55)}",
    ".bt-link{color:var(--accent-cyan,#2a7);text-decoration:none}.bt-link:hover{text-decoration:underline}",
    "@media (max-width:720px){.bt-markets{grid-template-columns:minmax(0,1fr)}.bt-table{font-size:12px}.bt-table th,.bt-table td{padding:5px 4px}}"
  ].join("");
  document.head.appendChild(css);
})();
