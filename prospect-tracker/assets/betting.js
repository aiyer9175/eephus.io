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
                  "validation", "mybets"];
  var SECTION_PAT = SECTIONS.join("|");
  var SECTION_LABELS = {
    potd: "Pick of the Day", teams: "Team Bets", props: "Player Props",
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
    return AUX_URL[key] + " did not load, so this panel has nothing to read. " +
      "It is written by the nightly build; a missing file means the build has " +
      "not run since the lane that writes it shipped.";
  }

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

    rows.push('<div class="bt-panel-sub">When does that change</div>');
    rows.push("<p>One dated snapshot lands per night, and a completed game becomes gradable " +
      "only once a snapshot predates it. So the honest sample starts at games played on or " +
      "after " + (cov.earliest_gradable_game_date ? esc(cov.earliest_gradable_game_date) :
        "the first night the snapshot runs") + ", and it grows until it reaches " +
      (need == null ? "the threshold" : need) + ". The arrival rate behind that is " +
      "MEASURED, not assumed off a schedule: Clock A on the Validation tab carries it " +
      "with the window it was counted over. A projection off a measured rate is still " +
      "a projection and is labelled as one there.</p>");
    if (v.generated_at) {
      rows.push('<div class="bt-asof">Backtest artifact generated ' + esc(v.generated_at) +
        (v.model_version ? " &middot; " + esc(v.model_version) : "") + "</div>");
    }
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
      segs.push(fhSeg("close", "unknown", true));
      segs.push(fhSeg("board", "unknown", true));
    } else {
      // OPEN. The capture the board was actually priced from, which is the one
      // that matters; `odds_kind` says which half of the day it is.
      var cap = st.odds_captured_at ? String(st.odds_captured_at).slice(0, 10) : null;
      segs.push(fhSeg("odds " + (st.odds_kind || "open"), cap || "none cached", !cap));
      // CLOSE. Zero is the state this strip exists for, and it is stated in
      // capitals because it is not a degraded reading of a working job, it is
      // a job that has never run.
      var nClose = fh ? fh.n_slates_with_close : null;
      var nSlates = fh ? fh.n_slates : null;
      var closeTxt, closeWarn;
      if (!fh) { closeTxt = "not measured"; closeWarn = true; }
      else if (!nClose) { closeTxt = "NEVER CAPTURED"; closeWarn = true; }
      else if (nClose < nSlates) { closeTxt = nClose + " of " + nSlates + " slates"; closeWarn = true; }
      else { closeTxt = "all " + nSlates + " slates"; closeWarn = false; }
      segs.push(fhSeg("close", closeTxt, closeWarn));
      segs.push(fhSeg("board", d.slate_date || "unknown", !d.slate_date));
      segs.push(fhSeg("games", String(d.n_games == null ? 0 : d.n_games),
                      !(d.n_games)));
    }
    var diag = (fh && fh.diagnosis) ? String(fh.diagnosis) : "";
    host.className = "bt-fh" + (!fh || !fh.n_slates_with_close ? " bt-fh-red" : "");
    host.setAttribute("role", "status");
    host.innerHTML = '<div class="bt-fh-line"' +
      (diag ? ' title="' + esc(diag) + '"' : "") + ">" +
      '<span class="bt-fh-hd">FEED</span>' + segs.join("") +
      (fh && !fh.n_slates_with_close
        ? '<span class="bt-fh-note">no close snapshot exists, so no pick on this ' +
          "page can ever be graded against the closing line</span>"
        : "") + "</div>";
  }

  // ---- model banner ---------------------------------------------------------
  function renderBanner() {
    renderFeedHealth();
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

  // ---- section: the two published slots -------------------------------------
  // THE SLOTS ARE DECLARED, NOT HARD-CODED INTO THE RENDERER, so a third slot
  // added server-side needs one row here and inherits the badge, the sentence
  // and the empty state rather than a new copy of all three.
  var SLOTS = [
    { key: "pick_of_the_day", title: "Pick of the Day",
      lead: "The side the model is most confident in, among prices in the normal range." },
    { key: "longshot_of_the_day", title: "Longshot Value of the Day",
      lead: "The best expected value at a long price. It will lose most nights; " +
            "that is what a long price means." }
  ];

  // The per-slot block of `pick_meta`, with the top-level block as the fallback
  // for a payload built before the slots existed. Returning the top level is
  // safe here because the fields the callers read (provisional, min_edge,
  // basis) have the same meaning at both levels; what the older shape cannot
  // supply is the slot's own reason, and the callers check for that.
  function slotMeta(key) {
    var m = (S.data && S.data.pick_meta) || {};
    return ((m.slots || {})[key]) || m;
  }

  function floorText(m) {
    if (!m || m.min_edge == null) return "the minimum edge";
    return pct(m.min_edge, 1) + (m.provisional === false ? " measured threshold"
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
      esc("This pick is published against a policy floor, not a validated " +
          "threshold. The model is unvalidated.") + '">provisional</span>';
  }

  // The sentence a reader who does not know what a de-vigged probability is can
  // still act on. Built entirely from served fields; it computes nothing.
  function pickSentence(p) {
    var who = esc(p.label || p.side || "this side");
    var s = "Our model gives " + who + " about a " + pct(p.model_prob, 0) +
      " chance to cash. The price of " + fmtOdds(p.odds) + " " +
      gl("implies", "implied_probability") + " " +
      (p.implied_prob != null ? pct(p.implied_prob, 0) + ", which is " +
        pct(p.market_fair_prob, 0) + " once the book's " + gl("cut", "vig") +
        " is taken out" : pct(p.market_fair_prob, 0) + " after the book's " +
        gl("cut", "vig") + " is taken out") +
      ". The model and the market disagree by " + signed(p.edge * 100, 1) +
      " points, and that gap is the " + gl("edge", "bet_edge") + ".";
    return "<p>" + s + "</p>";
  }

  function unitLine(p, m) {
    var bits = [];
    bits.push("Shown at " + num(p.suggested_units == null ? p.stake_units
                                                          : p.suggested_units, 1) +
      "u flat.");
    bits.push("Recorded on the public record at " + num(p.stake_units, 1) +
      "u, the same as every other pick, because a record kept in variable " +
      "stakes cannot be audited from its own rows.");
    var kq = (p.kelly_quarter != null) ? p.kelly_quarter
      : (p.kelly_full != null ? p.kelly_full / 4 : null);
    var chipHtml = (kq == null) ? "" :
      '<span class="bt-numchip bt-numchip-info"><span class="bt-numchip-l">Quarter ' +
      gl("Kelly", "kelly_criterion") + '</span><span class="bt-numchip-v">' +
      pct(kq, 1) + "</span></span>";
    return "<p>" + bits.join(" ") + " Kelly is informational here and never a " +
      "stake: full Kelly is only optimal if the probability is right, and this " +
      "model's probabilities have not been checked out of sample.</p>" +
      (chipHtml ? '<div class="bt-pick-nums">' + chipHtml + "</div>" : "") +
      (m && m.provisional !== false
        ? note("This is a " + gl("provisional pick", "provisional_pick") +
               ". It cleared a " + pct(m.min_edge, 1) + " " +
               gl("policy floor", "policy_floor") + ", not a measured " +
               "threshold, because the model is not validated. Nothing on this " +
               "page is advice.")
        : "");
  }

  // A WHOLE-NUMBER TOTAL REFUNDS SOME OF THE TIME, and the page said nothing.
  // `p_push` is the model's own mass exactly on the line, served on the row;
  // the two sides beside it are already conditional on it not landing. The
  // served EV carries the (1 - p_push) factor, so this line is what makes that
  // number legible rather than a discount nobody can see the reason for.
  function pushLine(p) {
    if (!p || p.p_push == null || !(p.p_push > 0)) return "";
    var pt = (p.point != null) ? p.point : null;
    var whole = (pt != null && Math.abs(pt - Math.round(pt)) < 1e-9);
    if (!whole) return "";
    return "<p>" + esc(String(Math.round(pt))) + " is a push " + pct(p.p_push, 1) +
      " of the time. A push returns the stake, so the expected value above is the " +
      "conditional value scaled by the " + pct(1 - p.p_push, 1) +
      " of the time the bet resolves at all.</p>";
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
    return note("Margin model: a one-parameter dispersion correction was fitted at alpha " +
      num(dr.alpha, 5) + " and its pre-registered gate returned <strong>" + verdict +
      "</strong>, so it is NOT served. This price comes from the Poisson difference, " +
      "which puts too little mass in the tails. The full grid is on the Validation tab.");
  }

  function pickCard(slot) {
    var d = S.data;
    var p = d[slot.key];
    var m = slotMeta(slot.key);
    var hd = '<div class="bt-pick-hd">' + esc(slot.title) + " " + provBadge(m) + "</div>";
    if (!p) {
      // THE HONEST EMPTY STATE. It names the floor it could not clear, and it
      // says the floor is not lowered to fill the slot, because a threshold
      // invented to make a pick appear is the single most dishonest number this
      // module could publish.
      var why = (m && m.reason) || d.pick_reason || "";
      return '<div class="bt-pick bt-pick-empty">' + hd +
        '<div class="bt-pick-sel bt-dim">Nothing qualifies today</div>' +
        "<p>" + esc(why) + "</p>" +
        "<p>The floor is " + pct(m.min_edge, 1) + ", the same one every other slot " +
        "clears, and it is never lowered to make a pick appear. An empty slot is " +
        "the honest answer to a slate with nothing on it.</p></div>";
    }
    // THE REDACTED SLOT (D16). The preview slice keeps the whole trust surface
    // (validation state, record, publish blockers) and withholds the SELECTION
    // only: market and floor, no side, no price, no book, no numbers. That is
    // the only shape in which a gate can exist without the free tier losing the
    // ability to check the process, and it is why the redaction is a server
    // rewrite rather than a client that hides fields it was sent.
    if (p.redacted) {
      return '<div class="bt-pick bt-pick-redacted">' + hd +
        "<p class=\"bt-pick-lead\">" + esc(slot.lead) + "</p>" +
        '<div class="bt-pick-sel bt-dim">Selection withheld</div>' +
        '<div class="bt-pick-meta">' + esc(p.market || "market not stated") +
        " &middot; cleared " + (p.min_edge_used == null ? "the floor"
                                                        : pct(p.min_edge_used, 1)) +
        "</div>" +
        "<p>" + esc(p.redaction_note || ("This slot has a pick. The preview slice " +
          "carries its market and the floor it cleared, and not the side, the price " +
          "or the book.")) + "</p>" +
        note("Everything needed to judge the pick is still on this page: the " +
          "validation state, the two clocks, the gate table and the public record " +
          "are never gated. What is behind the gate is the selection, not the " +
          "evidence.") + "</div>";
    }
    // THE CAVEAT SLOT CARRIES BOTH LINES. The row's own caveat says the market
    // is one of the two the margin model is worst at; the dispersion line says
    // what was done about that and what the gate returned.
    var shaped = (p.market === "runline" || p.market === "total");
    var caveat = (p.caveat ? note(esc(p.caveat)) : "") + dispersionLine(shaped);
    return '<div class="bt-pick">' + hd +
      "<p class=\"bt-pick-lead\">" + esc(slot.lead) + "</p>" +
      '<div class="bt-pick-sel">' + esc(p.label || p.side || "") + " " +
      fmtOdds(p.odds) + "</div>" +
      '<div class="bt-pick-meta">' + esc(p.matchup || "") + " &middot; " +
      esc(p.market || "") + " &middot; " + esc(p.book || "") + "</div>" +
      pickSentence(p) + pushLine(p) +
      '<div class="bt-pick-nums">' +
      chip("Model", pct(p.model_prob)) + chip("Market fair", pct(p.market_fair_prob)) +
      chip("Edge", signed(p.edge * 100, 1) + "%") +
      chip("EV / unit", signed(p.ev_per_unit, 3)) + "</div>" +
      caveat + unitLine(p, m) + "</div>";
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

  function pickCensus() {
    var d = S.data || {};
    var meta = d.pick_meta || {};
    if (meta.blocked) {
      return note("<strong>Nothing was ranked.</strong> " +
        esc(meta.blocked_reason || "the selection rule never ran") + ".");
    }
    var n = pricedSideCount(d.team_bets);
    var m = meta.n_floor_clearing_sides;
    var band = ((meta.slots || {}).pick_of_the_day || {}).band || "the price band";
    var floor = (meta.min_edge == null) ? "the floor" : pct(meta.min_edge, 1);
    return note("<strong>Census.</strong> " + n + " sides priced across " +
      (d.n_games || 0) + " games, " + (m == null ? "an unreported number of" : m) +
      " cleared the " + esc(floor) + " floor, and none of those are inside " +
      esc(band) + ". That is a measurement of tonight's board, not a failure to " +
      "load one: the board above is priced and the floor was not lowered to fill " +
      "a slot.");
  }

  function renderPick() {
    var d = S.data;
    var out = [];
    if (!d) {
      return empty("Pick of the day is unavailable",
        "The betting payload has not been built yet. Check back after the next build.");
    }
    var any = SLOTS.some(function (s) { return !!d[s.key]; });
    out.push(SLOTS.map(pickCard).join(""));

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
        "</div><p>" + esc(noPickHeadline(vstate())) + "</p>" + lines +
        "<p>These are the standing reasons the model is not validated. They stay " +
        "on the page whether a pick ships or not, because a provisional pick does " +
        "not make any of them untrue.</p></div>");
    }

    // THE PANELS ARE COLLAPSED, NOT REMOVED. Every word of the contamination
    // account, the gate table and the backtest is still here, one click away
    // and summarised in a sentence above the toggle. Leading a casual reader
    // straight into it taught him nothing; hiding it would be dishonest. This
    // is the only arrangement that is neither.
    out.push(trustTopline());
    out.push('<details class="bt-details"><summary class="bt-details-sum">' +
      "How much should you trust this? Open the full accounting" +
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
    var s = "Short version: this model is NOT validated. ";
    if (need != null) {
      s += "The honest backtest has graded " + (have == null ? "-" : have) +
        " of the " + need + " games it needs before any edge threshold can be " +
        "measured, so the picks above clear a " + pct(m.min_edge, 1) +
        " floor that was chosen as policy, not fitted to anything. ";
    } else {
      s += "No minimum edge has been measured, so the picks above clear a floor " +
        "that was chosen as policy, not fitted to anything. ";
    }
    s += "Treat them as a labelled experiment being logged in public.";
    return note(s);
  }

  // ===========================================================================
  // SECTION: VALIDATION
  // ===========================================================================
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
        '<div class="bt-headline-hd">The honest backtest has graded nothing yet</div>' +
        "<p>The vintage mode is the only one that is out of sample, and it has " +
        (b && b.status ? esc(b.status) : "no graded games") + ". Every Brier on this " +
        "page is from a contaminated mode whose features contain the games it grades.</p></div>";
    }
    var sk = b.skill_vs_home_base || {};
    var d = sk.delta;
    var verb = (d == null) ? "has no measured margin against"
      : (d < 0 ? "LOSES to"
              : (sk.beats_baseline_95 ? "beats" : "does not significantly beat"));
    return '<div class="bt-headline bt-headline-warn">' +
      '<div class="bt-headline-hd">The honest backtest ' + verb +
      " &quot;always take the home team&quot;</div>" +
      "<p>Out of sample, on " + n + " vintage-graded games: model " +
      gl("Brier", "brier_score") + " " + num(b.brier, 5) + " against a home-baseline " +
      num(b.brier_home_base, 5) + ", accuracy " + pct(b.accuracy, 2) + ". Paired " +
      "per-game skill " + signed(d, 6) + " at t = " + num(sk.t, 3) +
      ", one-sided 95% bar 1.645.</p>" +
      '<div class="bt-pick-nums">' +
      chip("Games", n) + chip("Brier", num(b.brier, 5)) +
      chip("Home base", num(b.brier_home_base, 5)) +
      chip("Accuracy", pct(b.accuracy, 2)) +
      chip("Skill", signed(d, 6)) + chip("t", num(sk.t, 3)) + "</div>" +
      "<p>Lower Brier is better, so a model above its own baseline is worse than the " +
      "baseline. This is the number that decides whether anything on this site may be " +
      "published as a pick, and it is not close to deciding it yes.</p></div>";
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
      '<div class="bt-clock-q">Has the model been graded on enough games it could not see?</div>',
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
      rows.push(note("That day count is a MEASURED rate applied forward, not a schedule. " +
        esc(rate ? rate.basis : "")));
    }
    if (c && c.may_go_backwards) {
      rows.push('<div class="bt-clock-fine">May go backwards: ' + esc(c.may_go_backwards) +
        "</div>");
    }
    if (!c) rows.push(note(esc(auxMissing("learning")) +
      " The count above is read from the payload; the arrival rate is not."));
    return '<div class="bt-clock">' + rows.join("") + "</div>";
  }

  function clockB() {
    var L = ((aux("learning") || {}).latest) || {};
    var c = (L.clocks || {}).graded_price_history || null;
    var rows = ['<div class="bt-clock-hd">Clock B &middot; settled paper bets, per tag</div>',
      '<div class="bt-clock-q">Does any edge threshold clear an ROI lower bound of zero, ' +
      "measured per selection rule?</div>"];
    if (!c) {
      rows.push(note(esc(auxMissing("learning"))));
      return '<div class="bt-clock">' + rows.join("") + "</div>";
    }
    var tags = c.by_tag || {};
    var keys = Object.keys(tags).sort();
    rows.push('<div class="bt-scroll mlbstats-scroll"><table class="bt-table mlbstats-table">' +
      '<thead><tr><th class="bt-l">Tag</th><th>Settled</th><th>Need</th>' +
      "<th>Per day</th><th>Days at that rate</th><th>State</th></tr></thead><tbody>" +
      keys.map(function (k) {
        var t = tags[k] || {};
        var r = t.rate || {}, e = t.eta || {};
        return '<tr><td class="bt-l">' + esc(k) + "</td><td>" +
          (t.have == null ? "-" : t.have) + "</td><td>" +
          (t.need == null ? (c.need_per_tag == null ? "-" : c.need_per_tag) : t.need) +
          "</td><td>" + num(r.per_day, 3) + "</td><td>" +
          (e.days == null ? "-" : e.days) + "</td><td>" +
          '<span class="bt-tag ' + (t.ready ? "bt-tag-ok" : "bt-tag-warn") + '">' +
          (t.ready ? "ready" : "short") + "</span></td></tr>";
      }).join("") + "</tbody></table></div>");
    rows.push(note(esc(c.why_per_tag || "")));
    if (c.cost) rows.push('<div class="bt-clock-fine">' + esc(c.cost) + "</div>");
    return '<div class="bt-clock">' + rows.join("") + "</div>";
  }

  // A bar, not a chart library. Width is a percentage of the served need, and
  // it is clamped at 100 so an overshoot cannot render past its own box.
  function meter(have, need) {
    if (have == null || !need) return "";
    var f = Math.max(0, Math.min(1, Number(have) / Number(need)));
    return '<div class="bt-meter" role="img" aria-label="' +
      esc(have + " of " + need) + '"><span class="bt-meter-fill" style="width:' +
      (f * 100).toFixed(1) + '%"></span></div>' +
      '<div class="bt-clock-fine">' + pct(f, 1) + " of the way there</div>";
  }

  function clocksPanel() {
    return '<div class="bt-panel"><div class="bt-panel-hd">Two clocks, and they are not ' +
      "the same clock</div>" +
      "<p>One counts GAMES the model was graded on out of sample. The other counts " +
      "SETTLED PAPER BETS, one row per selection rule. They open different gates and " +
      "they may never be added together: nobody is waiting on 600 bets, and nobody is " +
      "waiting on 100 games.</p>" +
      '<div class="bt-clocks">' + clockA() + clockB() + "</div></div>";
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
      rows.push('<div class="bt-panel-sub">Per market, where the dispersion shows up</div>');
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
        " Read the model column against the market column on the runline and the total: " +
        "a Poisson margin puts too little mass in the tails, so those two are where a " +
        "shape error is visible. n is " + (any.n == null ? "-" : any.n) +
        " canonical rows per market, which is not enough to conclude anything from."));
    }
    return '<div class="bt-panel">' + rows.join("") + "</div>";
  }

  // The gate returned INDETERMINATE and it is rendered as INDETERMINATE.
  // `verdict` GOVERNS: `passed` is one pre-registered split, the sweep is the
  // ship decision, and the two genuinely disagree right now. Rendering the
  // boolean would publish a pass the module refused to serve.
  function dispersionPanel() {
    var e = aux("evald") || {};
    var dr = e.run_dispersion || null;
    var rows = ['<div class="bt-panel-hd">Run dispersion: the margin model gate</div>'];
    if (!dr) {
      var L = ((AUX.learning || {}).latest) || {};
      var d2 = L.dispersion || null;
      rows.push("<p>" + esc(auxMissing("evald")) + "</p>");
      if (d2) {
        rows.push('<div class="bt-kv">' + kv("Status", esc(d2.status || "-")) +
          kv("Alpha", num(d2.alpha, 5)) +
          kv("Served", d2.served ? "yes" : "no") + "</div>");
        rows.push(note("Read from data/betting_learning.json, which carries the single " +
          "split and NOT the split-quantile sweep the verdict is taken from."));
      }
      return '<div class="bt-panel">' + rows.join("") + "</div>";
    }
    var sens = dr.sensitivity || {};
    var verdict = String(dr.verdict || sens.verdict || "unknown");
    var cls = verdict === "pass" ? "bt-tag-ok" : "bt-tag-warn";
    rows.push("<p><strong>Verdict: " +
      '<span class="bt-tag ' + cls + '">' + esc(verdict) + "</span></strong> " +
      "Not a pass and not a failure. " + esc(dr.verdict_note || "") + "</p>");
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
      rows.push(note("<strong>Both honest readings are above.</strong> The amended " +
        "criterion clears the bar at some split quantiles and misses it at others, and " +
        "the home side alone misses it at every one. " + esc(sens.rule || "")));
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

  function renderValidation() {
    var v = vstate();
    var out = [honestResult(), clocksPanel()];
    out.push('<div class="bt-subhd">The three gates on a published pick</div>');
    out.push(validationPanel());
    out.push(calibrationPanel());
    out.push(dispersionPanel());
    if (v && v.generated_at) {
      out.push('<div class="bt-asof">Validation state read from ' +
        esc(v.artifact || "data/betting_model_eval.json") + ", generated " +
        esc(v.generated_at) + ". The clocks and the calibration ledger are read from " +
        esc(AUX_URL.learning) + ".</div>");
    }
    return out.join("");
  }

  // ---- section: the record --------------------------------------------------
  // THREE PANELS, and the validation accounting is no longer one of them: it
  // moved to its own tab. What is here is the record itself, the closing-line
  // grade on the positions in it, and the pre-registered list of conditions a
  // pick has to clear before it may enter the record at all.
  function renderRecord() {
    var d = S.data;
    return recordPanel(d ? d.record : null) + clvPanel() + publishBlockerPanel() +
      '<div class="bt-panel"><div class="bt-panel-hd">How a pick gets graded</div>' +
      "<p>Every published pick carries the timestamp, the book, the price at post " +
      "and a flat one " + gl("unit", "betting_unit") + ". It settles won, lost or " +
      "void, and it is then graded a second time against the closing line.</p>" +
      "<p>" + gl("Closing line value", "clv") + " is the honest test. Beating the close means the market " +
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
      rows.push(note("Lower " + gl("Brier", "brier_score") + " is better. " + skillSentence(blocks) +
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
    // THE JOIN, NAMED. `record` is not the record file: it is the record joined
    // to the settlement sidecar and to the CLV sidecar on bet_id. Neither
    // `beat_close` nor `clv_pct` can ever be a byte of a record row, because
    // rows are immutable and CLV lands hours later, so a summary computed off
    // the record alone reported "not graded yet" over a fully graded record.
    var sha = (r || {}).chain_sha;
    var chain = sha ? ('<div class="bt-clock-fine">Chain ' +
      '<code class="bt-sha">' + esc(sha) + "</code>. " +
      esc((r || {}).chain_note || "") + " Archive this value: a later record that " +
      "still contains it as one of its prefix hashes is an append, and one that does " +
      "not is a rewrite.</div>") : "";
    return '<div class="bt-panel"><div class="bt-panel-hd">The public record</div>' + body +
      "<p>Joined across three files on bet_id: the append-only record, the settlement " +
      "sidecar and the closing-line sidecar. Verification: recompute the chain by " +
      "folding sha256 row by row over " + esc(url) + " and compare it to the hash " +
      "below.</p>" + chain +
      "<p>" + esc((S.data && S.data.record_policy) ||
        "Append only. Rows are never edited or deleted; a correction is a new row.") + " " +
      'The raw file is <a class="bt-link" href="' + esc(url) + '">' + esc(url) + "</a>. " +
      'The sidecars are <a class="bt-link" href="' +
      esc((S.data && S.data.settlement_url) || "/data/betting_settlement.json") + '">' +
      esc((S.data && S.data.settlement_url) || "/data/betting_settlement.json") + "</a> and " +
      '<a class="bt-link" href="' + esc((S.data && S.data.clv_url) || AUX_URL.clv) + '">' +
      esc((S.data && S.data.clv_url) || AUX_URL.clv) + "</a>.</p></div>";
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
      rows.push('<div class="bt-panel-sub">Distribution, ' + h.n + " graded picks in ten " +
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
        rows.push("<p>Nothing has a closing-line grade. Every row the sidecar looked at, " +
          "and why:</p>");
        rows.push('<div class="bt-scroll mlbstats-scroll"><table class="bt-table mlbstats-table">' +
          '<thead><tr><th class="bt-l">Reason</th><th>Rows</th></tr></thead><tbody>' +
          keys.map(function (k) {
            return '<tr><td class="bt-l">' + esc(k) + "</td><td>" + reasons[k] + "</td></tr>";
          }).join("") + "</tbody></table></div>");
      } else if (!r.n_rows) {
        rows.push("<p>No pick has been published, so there is no position to grade " +
          "against a close. The sidecar is derived from the record and is not " +
          "requested until the record has a row in it.</p>");
      } else {
        rows.push("<p>No closing-line grade exists. " + esc(auxMissing("clv")) + "</p>");
      }
      rows.push(note("CLV is unrecoverable after the fact. A slate whose close was never " +
        "captured can never be graded, whatever runs tomorrow, which is why the feed strip " +
        "at the top of this page leads with it."));
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
      rows.push("<p>This payload carries no publish-blocker list, which means it was " +
        "built before that lane existed. The record above is the only evidence of what " +
        "has been published.</p>");
      return '<div class="bt-panel">' + rows.join("") + "</div>";
    }
    var nOpen = 0;
    bl.forEach(function (b) { if (b.open) nOpen += 1; });
    rows.push("<p>" + nOpen + " of " + bl.length + " are open. A pick is written to the " +
      "public record only when every one of them is.</p>");
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
        "price a game.</strong> " + (nDrop || 0) + " were already under way when the " +
        "snapshot was taken, and " + (nMiss || 0) + " games had a candidate event too " +
        "far from first pitch to be the same game. Those games are still on the board " +
        "below, marked unpriced, because an absent row reads as an absent game.");
    }
    var thr = pickFloor();
    if (hasMarket && thr != null) {
      head += note("A <strong>best value</strong> badge marks the single side in a " +
        "game with the largest " + gl("edge", "bet_edge") + " clearing the same " +
        esc(floorText((S.data && S.data.pick_meta) || {})) + " the picks above " +
        "use, so the badge and the picks can never disagree about the bar. A game " +
        "with no badge had nothing clear it, and that absence is information: it " +
        "means the model and the market agree about that game.");
    }
    return head + bets.map(gameCard).join("");
  }

  // THE BADGE AND THE PICKS READ ONE NUMBER. The threshold comes from
  // `pick_meta.min_edge`, which is the same resolved floor the server used to
  // choose the slots, so a row can never be badged as value on the board while
  // being below the bar the picks were held to. Hard-coding it here is how the
  // two would drift the day the measured threshold replaces the policy floor.
  function pickFloor() {
    var m = (S.data && S.data.pick_meta) || {};
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

  // The match window, in minutes. MIRRORS betting_export.EVENT_MATCH_MAX_MINUTES
  // and is read from the payload the moment `status` carries it; the literal is
  // the fallback for a payload that does not, and it exists only so the reason
  // on an unpriced row is a number rather than a shrug.
  function matchWindowText(st) {
    var mins = (st && st.event_match_max_minutes != null)
      ? Number(st.event_match_max_minutes) : 180;
    return (mins % 60 === 0) ? (mins / 60) + "h" : mins + " min";
  }

  function gameCard(b) {
    var m = b.model || {};
    var st = (S.data || {}).status || {};
    var best = bestValueSide(b, pickFloor());
    var badge = best ? ' <span class="bt-tag bt-tag-ok bt-bestval">best value ' +
      esc(best.label || best.side || "") + " " + fmtOdds(best.odds) + "</span>" : "";
    // UNPRICED IS A STATE, NOT AN OMISSION. The board carries the game and says
    // which filter left it without prices, because a game that vanished off the
    // page reads as a game that is not being played.
    if (st.odds_feed === "ok" && !b.odds_event_id && !b.market) {
      badge += ' <span class="bt-tag bt-tag-warn bt-unpriced" title="' +
        esc("betting_export.match_event refused the candidate event; see " +
            "status.n_games_unpriced_time_mismatch and n_events_dropped_in_progress") +
        '">unpriced: no pre-game odds event within ' + matchWindowText(st) +
        " of first pitch</span>";
    }
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
                              b.total.sides, best));
    }
    else blocks.push('<div class="bt-market"><div class="bt-market-hd">Total</div>' +
      '<div class="bt-faironly">Model fair total ' + num(m.fair_total, 2) +
      ". No posted line to compare.</div></div>");

    return '<div class="bt-game">' + hd + probs + sp +
      '<div class="bt-markets">' + blocks.join("") + "</div>" + devigPanel(b) + "</div>";
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
      '<div class="bt-hold">Fair probabilities are ' + gl("de-vigged", "devig") +
      " by the proportional method from the named book only. Rule: " +
      esc(mk.fair_book_rule || "min_hold") + ".</div>";
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
  function marketBlock(title, rows, best) {
    if (!rows || !rows.length) return "";
    var hasBook = rows.some(function (r) { return r.odds != null; });
    var head = "<tr><th class=\"bt-l\">" + title + "</th><th>Model</th>" +
      (hasBook ? "<th>Price</th><th>" + gl("Fair", "fair_line") + "</th><th>" +
        gl("Edge", "bet_edge") +
        "</th><th>" + gl("EV/u", "ev_per_unit") + "</th><th>" +
        gl("Kelly", "kelly_criterion") + "</th>" : "<th>Fair price</th>") + "</tr>";
    var body = rows.map(function (r) {
      var cells = "<td class=\"bt-l\">" + esc(r.label || r.side) +
        (r === best ? ' <span class="bt-tag bt-tag-ok bt-bestval">best value</span>' : "") +
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
      case "validation": html = renderValidation(); break;
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
    ".bt-pick-hd{font:700 11px/1 var(--font-retro,monospace);color:var(--accent-green,#3a9);text-transform:uppercase;letter-spacing:.06em;display:flex;align-items:center;gap:8px;flex-wrap:wrap}",
    ".bt-pick-sel{font:700 20px/1.2 var(--font-retro,monospace);color:var(--text-primary);margin:6px 0}",
    ".bt-pick-meta{font-size:12px;color:var(--text-tertiary);margin-bottom:8px}",
    ".bt-pick p{font-size:12.5px;color:var(--text-secondary);margin:0 0 8px}",
    ".bt-pick-lead{color:var(--text-tertiary)}",
    // An empty slot must not read as a failed load. It keeps the card frame and
    // the heading, and loses only the accent that says "here is a pick".
    ".bt-pick-empty{border-color:var(--border,#333)}",
    ".bt-pick-empty .bt-pick-hd{color:var(--text-tertiary)}",
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
    ".bt-meter{height:8px;border:1px solid var(--border,#333);margin:8px 0 2px;background:var(--bg-secondary)}",
    ".bt-meter-fill{display:block;height:100%;background:var(--accent-cyan,#2a7)}",
    ".bt-bar{display:inline-block;height:9px;min-width:1px;background:var(--accent-cyan,#2a7)}",
    ".bt-sha{font:600 10px/1 var(--font-retro-mono,var(--font-retro,monospace));color:var(--text-secondary);word-break:break-all}",
    ".bt-unpriced{white-space:normal}",
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
    "}"
  ].join("");
  document.head.appendChild(css);
})();
