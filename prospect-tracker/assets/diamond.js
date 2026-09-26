// Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
// Unauthorized copying of this file, via any medium is strictly prohibited
// Proprietary and confidential
// Written by Noah J. Dengler (@ARKNDJL), 2026
//
// /diamond/ - the Diamond Pass page client.
//
// The page itself is server-rendered by build_site.build_diamond(), so it is
// complete and readable with JavaScript off. This file does three things on
// top of that, and only three:
//
//   1. RECEIPTS. The accuracy numbers on a page that asks for money must come
//      from the artifact, not from a copywriter's memory. This reads
//      data/xfv_scoreboard_eval.json at render time and prints what is in it.
//      If the model gets worse, this page says so by itself. A hardcoded
//      "0.384" would have been a claim with a shelf life.
//   2. THE BETTING RECORD. Reads the joined record summary the betting board
//      serves (falling back to counting the raw append-only rows). While no
//      pick has posted the card says the record starts when the picks do,
//      which is the truth, instead of hiding the section.
//   3. A SIGN-IN AWARE CALL TO ACTION that only replaces the server-rendered
//      card once the account layer is configured and switched on. The static
//      card is the truth for every other build.
//
// NOTE FOR FUTURE EDITS: this page reads EVAL METRICS, never a player's eFV
// grade. If you ever add a grade here, it goes through the one basis rule
// (efv_board_scale.board_value on the export side), never a second scale.
//
// Nothing here throws when a payload is missing. Every fetch failure lands in
// a card that says what is absent and why, because a blank rectangle on a
// pricing page reads as a broken site.
(function () {
  "use strict";

  var SCOREBOARD_URL = "/data/xfv_scoreboard_eval.json";
  var RECORD_URL = "/data/betting_record.json";
  var CFG = (typeof window !== "undefined" && window.EEPHUS_DIAMOND) || {};

  function el(id) { return document.getElementById(id); }
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }
  function commas(n) {
    if (n == null || isNaN(n)) return "";
    return String(Math.round(n)).replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  }
  // Correlations and AUCs print at their artifact precision. These are model
  // diagnostics, not the "+" stats or FV grades that carry rounding rules.
  function dec(v, d) {
    return (v == null || isNaN(v)) ? null : Number(v).toFixed(d == null ? 3 : d);
  }
  // Just .card: the diamond-card class this used to add had zero CSS rules in
  // site.css or the injected sheet below, on any theme (checked 2026-08-16).
  function card(inner) { return '<div class="card">' + inner + "</div>"; }
  function note(msg) { return card("<p>" + esc(msg) + "</p>"); }
  // Glossary term span (assets/eephus-gl.js). Slugs are checked against
  // data/glossary.json before use: a [data-gl] whose slug the artifact does not
  // carry renders a term that looks interactive and defines nothing, which on a
  // page asking for money is worse than plain text.
  function gl(label, slug) {
    return '<span class="g-term" data-gl="' + esc(slug) + '">' + esc(label) + "</span>";
  }
  function wireGl(node) {
    try { if (node && window.EEPHUS_GL && EEPHUS_GL.wire) EEPHUS_GL.wire(node); }
    catch (e) { /* the glossary is enrichment; the page reads fine without it */ }
  }

  // Content stamp lookup. build_site emits window.EEPHUS_DATA_VERS on
  // /diamond/ with the scoreboard artifact's content hash; with a stamp the
  // read rides a versioned URL under DEFAULT caching, and without one the
  // no-cache revalidation stays exactly as it was.
  function stampedURL(url) {
    try {
      var vers = (typeof window !== "undefined" && window.EEPHUS_DATA_VERS) || null;
      var v = vers && vers[url.split("/").pop()];
      return v ? url + "?v=" + encodeURIComponent(v) : null;
    } catch (e) { return null; }
  }
  // `fresh` forces the revalidating read even on a page that emits stamps.
  // The betting record is the one caller: betting_record.json is mutated
  // INTRA-DAY by the close job with no page rebuild in between, so a
  // build-time stamp would pin a week-stale copy under the /data/ max-age.
  // It must never enter EEPHUS_DATA_VERS (build_site's _data_vers_script
  // refuses betting names outright), and this flag keeps the record read
  // honest even if the map ever grew a rogue entry.
  function getJSON(url, fresh) {
    var stamped = fresh ? null : stampedURL(url);
    var opts = stamped ? undefined : { cache: "no-cache" };
    if (stamped) url = stamped;
    return fetch(url, opts).then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    });
  }

  // ---- 1. model receipts ----------------------------------------------------
  // Shape read (data/xfv_scoreboard_eval.json, written by the eFV scoreboard
  // eval): head_to_head.vs.<source>.{spearman,auc_contributor} each carrying
  // {n, efv, consensus, win, margin}. Anything absent is skipped rather than
  // faked, so an artifact that changes shape degrades to fewer tiles.
  // `resolvable` is the artifact's own verdict (verdict_vs_consensus.resolvable):
  // the eFV number takes the win colour only when the backtest itself resolves a
  // lead. Two numbers whose gap sits under the floor print in the same ink,
  // because colour is a claim too (tie-first repaint, 2026-08-16).
  function tile(label, ours, theirs, n, sub, resolvable) {
    var a = dec(ours), b = dec(theirs);
    if (a == null || b == null) return "";
    return '<div class="dm-tile">' +
      '<div class="dm-tile-lbl">' + esc(label) + "</div>" +
      '<div class="dm-tile-row"><span class="dm-tile-who">eFV</span>' +
        '<span class="dm-tile-val' + (resolvable ? " dm-ours" : "") + '">' + esc(a) + "</span></div>" +
      '<div class="dm-tile-row"><span class="dm-tile-who">' + esc(sub) + "</span>" +
        '<span class="dm-tile-val">' + esc(b) + "</span></div>" +
      (n ? '<div class="dm-tile-n">' + esc(commas(n)) + " players, same set</div>" : "") +
      "</div>";
  }

  function renderReceipts(doc) {
    var root = el("diamond-receipts");
    if (!root) return;
    var h2h = doc && doc.head_to_head;
    var vs = h2h && h2h.vs;
    var against = vs && (vs.prospx_consensus || vs.fangraphs || vs.mlb_pipeline);
    if (!against) {
      root.innerHTML = note("The scoreboard artifact carries no head-to-head block, so no comparison is shown.");
      return;
    }
    var who = against.label || "the public consensus";
    // THE VERDICT GATES THE PAINT (tie-first repaint, 2026-08-16). resolvable is
    // the artifact's own call on whether the observed gap clears the minimum this
    // backtest can resolve; until the artifact says true, no tile prints eFV in
    // the win colour and the card LEADS with the tie, because a green number over
    // a smaller grey one is a win claim whatever the prose under it says.
    var vv = h2h.verdict_vs_consensus;
    var resolvable = !!(vv && vv.resolvable);
    var sp = against.spearman || {};
    var auc = against.auc_contributor || {};
    // ONE FRAME OR NO TILES (2026-09-24). The tiles once came from the all base
    // years frame (eFV ahead) while the margin sentence under them came from the
    // vintage-matched frame (eFV behind, on about a quarter of the players), so a
    // reader who subtracted the tiles got the opposite sign of the sentence. The
    // exporter now builds both from one frame; if an artifact ever hands this
    // card two populations again, the tiles are withheld rather than printed
    // against a verdict they do not belong to.
    var sameFrame = !(vv && vv.n != null && sp.n != null && Number(vv.n) !== Number(sp.n));
    var tiles = sameFrame
      ? tile("Rank correlation with realized career WAR", sp.efv, sp.consensus, sp.n, who, resolvable) +
        tile("Contributor AUC", auc.efv, auc.consensus, auc.n, who, resolvable)
      : "";
    var frameHTML = !sameFrame
      ? '<p class="dm-fine">The tiles are withheld: this scoreboard scored them on ' +
        esc(commas(sp.n)) + " players and the verdict below on " + esc(commas(vv.n)) +
        ", so they do not describe the same comparison.</p>"
      : (h2h.vs_frame_note
        ? '<p class="dm-fine">Tiles and margin share one frame: ' + esc(h2h.vs_frame_note) + ".</p>"
        : "");
    if (!tiles && sameFrame) {
      root.innerHTML = note("The scoreboard artifact carries no comparable metrics yet.");
      return;
    }
    // The discrimination half of the sentence is the artifact's too: the contributor
    // AUC cell carries a verdict word only when it survives the Holm correction
    // across the per-source family (owner answer FP3-3, 2026-09-25).
    var aucWord = auc.holm_verdict || null;
    var intro = resolvable
      ? "<p>Scored on the same players out of sample, forward-chained " + gl("backtest", "backtest") +
        ". Higher is better.</p>"
      : "<p>" + gl("eFV", "xfv") + " and the public consensus are statistically indistinguishable " +
        "on " + (aucWord ? "ordering" : "both ordering and discrimination") +
        ", scored on the same players out of sample, forward-chained " +
        gl("backtest", "backtest") + "." +
        (aucWord ? " On contributor AUC, after a correction for testing several sources, eFV " +
          esc(aucWord) + "." : "") + "</p>";
    // A LEAD IS NOT A RESULT UNTIL IT CLEARS THE FLOOR, AND A FLOOR IS NOT CHECKABLE
    // UNTIL IT NAMES ITS ESTIMATOR. These tiles used to print two numbers and let the
    // bigger one win, which is the bare-inequality pattern the eFV verdict gating
    // removed everywhere else. The artifact carries the minimum gap this backtest can
    // resolve at 95% (verdict_vs_consensus.mde95), so a lead inside it reads as the
    // tie it is.
    //
    // WHICH FLOOR THIS IS (comment de-numbered 2026-08-16: the values that used to
    // sit here belong to the artifacts, which move; a comment does not). vv.mde95 is
    // source_backtest.XFV_HEADTOHEAD_MDE95, a cluster paired bootstrap that resamples
    // players AND refits the forward chain on every draw. That is E_refit. B-L1
    // published a SECOND floor for this exact cell, E_cond, which holds the fit and
    // resamples the scored clusters only, and the two estimators have returned
    // OPPOSITE calls on one observed margin. So the floor never prints without its
    // estimator. The label comes from the artifact (verdict_vs_consensus.
    // mde95_estimator) when it carries one; the fallback is E_refit because that is
    // definitionally what XFV_HEADTOHEAD_MDE95 measures. Current values for both
    // floors live in data/xfv_scoreboard_eval.json verdict_vs_consensus and
    // data/xfv_power_eval.json partb_floors; read them there, never from here.
    //
    // "MORE RESOLVED COHORTS, NOT A BETTER MODEL" stays the closing clause of the
    // tie copy. A Phase 1 proposal wanted to rewrite it around a refit-variance
    // share measured on a DIFFERENT statistic over a DIFFERENT pool, and it also
    // conflated a variance share with a floor share (floors scale as the square
    // root of variance). On THIS statistic most of the floor is removable by test
    // n, so cohorts really are what settles it. The per-cell shares are in
    // data/xfv_power_eval.json partb_floors; do not re-import any of them here.
    var verdictHTML = "";
    if (vv && vv.delta != null && vv.mde95 != null) {
      var lead = (vv.delta >= 0 ? "+" : "") + dec(vv.delta);
      var est = (vv.mde95_estimator || "E_refit") +
        (vv.mde95_status === "carried" ? ", carried from " + (vv.mde95_carried_from || "an earlier frame") : "");
      verdictHTML = '<p class="dm-fine">Rank correlation margin ' + esc(lead) +
        " over " + esc(who) + ". " + (resolvable
          ? "Clears the " + esc(dec(vv.mde95)) + " this backtest resolves at 95% (" +
            esc(est) + "): a real lead."
          : "Under the " + esc(dec(vv.mde95)) + " this backtest resolves at 95% (" +
            esc(est) + "): a tie whatever its sign. More resolved cohorts, not a " +
            "better model, settle it.") +
        "</p>";
    }
    var arch = (h2h.by_archetype_vs_consensus || []).filter(function (a) {
      return a && a.spearman && a.spearman.efv != null;
    });
    var archHTML = "";
    if (arch.length) {
      // SAY WHICH METRIC. The table reads by_archetype_vs_consensus[].spearman
      // and nothing else, but it sits directly under two tiles carrying two
      // DIFFERENT numbers (rank correlation and contributor AUC) and named
      // neither of them, so the fine print names the metric.
      //
      // NO PER-ROW WIN PAINT (2026-08-16). The old green-on-the-higher-cell was
      // the bare-inequality pattern one level down: a win call on subgroup cells
      // that carry no resolvability floor at all. The raw numbers stay; the
      // fine print under the table says what they are and what they are not.
      archHTML = '<p class="dm-fine">Rank correlation with realized career ' +
        gl("WAR", "war") + ", by prospect group.</p>" +
        // The shared table dialect: .mlbstats-scroll + .mlbstats-table give the
        // sticky header, the frozen identity column and the horizontal scroller
        // this table never had, so the archetype rows cannot pan the page
        // sideways on a phone. .dm-table stays for the local colour rules.
        '<div class="mlbstats-scroll"><table class="dm-table mlbstats-table"><thead><tr>' +
        "<th>Group</th><th>" + gl("eFV", "xfv") + "</th><th>" + esc(who) + "</th><th>n</th>" +
        "</tr></thead><tbody>" +
        arch.map(function (a) {
          return "<tr><td>" + esc(a.label || a.archetype) + "</td>" +
            '<td class="dm-num">' + esc(dec(a.spearman.efv)) + "</td>" +
            '<td class="dm-num">' + esc(dec(a.spearman.consensus)) + "</td>" +
            '<td class="dm-num">' + esc(commas(a.n)) + "</td></tr>";
        }).join("") +
        "</tbody></table></div>" +
        '<p class="dm-fine">These are point estimates on small groups. No per-group winner is ' +
        "called: no row carries its own verdict.</p>" +
        (h2h.by_archetype_basis
          ? '<p class="dm-fine">Groups score ' + esc(h2h.by_archetype_basis) + ".</p>"
          : "");
    }
    var protocol = h2h.protocol ? "<p class=\"dm-fine\">" + esc(h2h.protocol) + "</p>" : "";
    // The scoring date, and a loud note when it is old. 21 days: the scoreboard
    // regenerates with the monthly rebuild, so three weeks late means a cycle
    // was missed, and a page that asks for money should say so itself.
    var asof = String((doc && (doc.generated_at || doc.as_of)) || "").slice(0, 10);
    var asofHTML = "";
    if (asof) {
      var ageDays = (Date.now() - Date.parse(asof)) / 86400000;
      asofHTML = '<p class="dm-fine">Scored as of ' + esc(asof) + "." +
        (isFinite(ageDays) && ageDays > 21
          ? " More than three weeks old: the last scoring run, not this week's."
          : "") + "</p>";
    }
    root.innerHTML = card(
      "<h3>eFV against the public consensus</h3>" +
      intro +
      (tiles ? '<div class="dm-tiles">' + tiles + "</div>" : "") +
      frameHTML +
      verdictHTML +
      archHTML +
      protocol +
      asofHTML +
      '<p class="dm-fine">Read from data/xfv_scoreboard_eval.json at page load.</p>'
    );
    wireGl(root);
  }

  function receiptsFailed(msg) {
    var root = el("diamond-receipts");
    if (!root) return;
    root.innerHTML = note(
      "The scoreboard did not load (" + (msg || "unknown error") + "). Its numbers come only from " +
      "data/xfv_scoreboard_eval.json, so none are shown.");
  }

  // ---- 2. betting record ----------------------------------------------------
  // THE SUMMARY, NOT THE ROWS (M12-14, 2026-09-25). data/betting_record.json is
  // a bare array of append-only rows, and a row never carries its result: the
  // result lives in the settlement sidecar and is joined on bet_id by
  // betting_export.record_summary. This card used to read doc.summary and
  // doc.picks off that array, found neither, and so would have said "No pick
  // published yet" on the day the first row posted. It now reads the joined
  // summary the betting board serves (the `record` block of the public preview
  // slice), and falls back to counting the array only when that slice does not
  // load, in which case it can say how many rows posted and nothing about
  // results.
  //
  // THE GRADING BASIS IS A SERVED FLAG (M12-04, 2026-09-25). Closing line value
  // was retired on 2026-09-07 (betting_export.SERVE_CLV). build_site bakes that
  // flag onto the mount as data-serve-clv, so every sentence here names the
  // basis the record is actually graded on, and no CLV row prints while it is
  // off.
  var PREVIEW_URL = "/data/betting_preview.json";

  function serveClv(root) {
    if (!root || typeof root.getAttribute !== "function") return false;
    return root.getAttribute("data-serve-clv") === "1";
  }
  function gradedOn(root) {
    return serveClv(root) ? "graded against the closing line" : "graded on its realized result";
  }
  function num(v) { return (v == null || isNaN(v)) ? null : Number(v); }
  // Percent in, percent out: record_summary serves roi_pct and avg_clv_pct as
  // percentages and beat_close_rate as a fraction, and each is formatted on its
  // own basis rather than guessed from its size.
  function signedPct(v) {
    var x = num(v);
    return x == null ? null : (x >= 0 ? "+" : "") + x.toFixed(1) + "%";
  }
  function ratePct(v) {
    var x = num(v);
    return x == null ? null : (x * 100).toFixed(1) + "%";
  }
  function statRow(label, value) {
    if (value == null || value === "") return "";
    return '<div class="dm-stat"><span class="dm-stat-lbl">' + esc(label) + "</span>" +
      '<span class="dm-stat-val">' + esc(value) + "</span></div>";
  }
  // One shape for both sources: {posted, settled, won, lost, push, net_units,
  // roi_pct, avg_clv_pct, beat_close_rate, asof}. Null means not known.
  function fromSummary(doc) {
    var s = doc && doc.record;
    if (!s || typeof s !== "object" || s.n_rows == null) return null;
    return {
      posted: num(s.n_rows) || 0, settled: num(s.n_settled) || 0,
      won: num(s.won) || 0, lost: num(s.lost) || 0, push: num(s.push) || 0,
      net_units: num(s.net_units), roi_pct: num(s.roi_pct),
      avg_clv_pct: num(s.avg_clv_pct), beat_close_rate: num(s.beat_close_rate),
      asof: doc.generated_at || null
    };
  }
  function fromRows(rows) {
    if (!Array.isArray(rows)) return null;
    // Rows do not carry results, so this fallback knows the posted count only.
    return { posted: rows.length, settled: null, asof: null };
  }
  function emptyRecord(reason) {
    var root = el("diamond-betting-record");
    if (!root) return;
    root.innerHTML = card(
      "<h3>Betting record</h3>" +
      "<p>No pick published yet. Each pick will carry its timestamp, book, posted odds and a flat " +
      "1-unit stake, and be " + gradedOn(root) +
      ". The file is append only.</p>" +
      (reason ? '<p class="dm-fine">' + esc(reason) + "</p>" : "")
    );
  }
  // POSTED IS NOT THE SAME AS GRADED. A record carrying picks that have not
  // settled has no wins and no losses, and the card says so rather than
  // falling into the no-picks sentence its own file contradicts.
  function ungradedRecord(nPosted, asof, resultsKnown) {
    var root = el("diamond-betting-record");
    if (!root) return;
    root.innerHTML = card(
      "<h3>" + esc(commas(nPosted)) + " pick" + (nPosted === 1 ? "" : "s") + " posted" +
        (resultsKnown ? ", none settled" : "") + "</h3>" +
      "<p>Each carries its timestamp, book, posted odds and a flat 1-unit stake, and is " +
      gradedOn(root) + " when it settles." +
      (resultsKnown ? " No pick is graded yet, so there is no record."
                    : " The results did not load, so none are shown.") + "</p>" +
      (asof ? '<p class="dm-fine">Record as of ' + esc(String(asof).slice(0, 10)) + ".</p>" : "")
    );
  }
  function renderRecord(rec) {
    var root = el("diamond-betting-record");
    if (!root) return;
    if (!rec || !rec.posted) { emptyRecord(""); return; }
    if (rec.settled == null) { ungradedRecord(rec.posted, rec.asof, false); return; }
    if (!rec.settled) { ungradedRecord(rec.posted, rec.asof, true); return; }
    var clv = serveClv(root);
    root.innerHTML = card(
      "<h3>The betting record</h3>" +
      '<div class="dm-stats">' +
        statRow("Record", rec.won + " - " + rec.lost + (rec.push ? " - " + rec.push : "")) +
        statRow("Picks settled", commas(rec.settled)) +
        statRow("Picks posted", commas(rec.posted)) +
        statRow("Net units", rec.net_units == null ? null
          : (rec.net_units >= 0 ? "+" : "") + rec.net_units.toFixed(2)) +
        statRow("ROI", signedPct(rec.roi_pct)) +
        (clv ? statRow("Average closing line value", signedPct(rec.avg_clv_pct)) +
               statRow("Beat the closing line", ratePct(rec.beat_close_rate)) : "") +
      "</div>" +
      "<p>Flat 1 unit per pick, append only. " + (clv
        ? "Closing line value: posted odds against the closing odds.</p>"
        : "Graded on realized results; closing line value is not captured.</p>") +
      (rec.asof ? '<p class="dm-fine">Record as of ' + esc(String(rec.asof).slice(0, 10)) + ".</p>" : "") +
      '<p class="dm-fine">21+. Informational and for entertainment only. Sports betting is not legal in ' +
      "every state. No affiliate links. If betting stops being fun, call 1-800-GAMBLER.</p>"
    );
  }
  function loadRecord() {
    // fresh:true on both reads: each mutates with the nightly and neither is
    // stamped (build_site's _data_vers_script refuses betting names).
    getJSON(PREVIEW_URL, true).then(function (doc) {
      var rec = fromSummary(doc);
      if (!rec) throw new Error("no record block");
      renderRecord(rec);
    }).catch(function () {
      getJSON(RECORD_URL, true).then(function (rows) {
        renderRecord(fromRows(rows));
      }).catch(function () {
        // 404 is the expected state before the first pick. Anything else lands
        // in the same honest card: there is no record to show.
        emptyRecord("");
      });
    });
  }

  // ---- 3. sign-in aware call to action -------------------------------------
  // THE STATIC CARD IS THE DEFAULT, NOT A FALLBACK (2026-08-16). The server
  // renders the truth for a build with no account layer: no signup exists, the
  // preview needs no account, founding status is honored when accounts open.
  // This function replaces that card ONLY when the account layer is configured
  // and switched on. The old version painted over it unconditionally with a
  // "Create a free account" button that had to disable itself when clicked,
  // which is a control whose honest state is not existing.
  function renderCTA() {
    var root = el("diamond-cta");
    if (!root) return;
    var A = window.EephusAccount;
    if (!A || !A.enabled || !A.enabled() || !A.ready) return;
    // Prices come from diamond-config.js via CFG, never from literals here: a
    // sentence with no price beats a price the config no longer carries.
    var price = CFG.price_usd_month != null ? CFG.price_usd_month : null;
    var founding = CFG.founding_rate_usd != null ? CFG.founding_rate_usd : null;
    var gated = !!CFG.gating;

    function paint(html) { root.innerHTML = html; }
    function signedOut() {
      paint(
        "<h3>" + (gated ? "Membership" : "Nothing to buy yet") + "</h3>" +
        "<p>" + (gated
          ? "Diamond is live" + (price != null ? " at $" + esc(price) + " a month" : "") + "."
          : "Free during the founding preview." +
            (price != null && founding != null
              ? " At launch: $" + esc(price) + " a month, $" + esc(founding) + " for founding members."
              : "")) + "</p>" +
        "<p>A free account keeps your watchlist, bet log and founding status across devices.</p>" +
        '<button type="button" class="dm-btn" data-diamond="signin">Create a free account</button>'
      );
      var b = root.querySelector('[data-diamond="signin"]');
      if (b) {
        b.addEventListener("click", function () {
          if (window.EephusUI && window.EephusUI.openAuthModal) {
            window.EephusUI.openAuthModal("signin");
          }
        });
      }
    }
    function signedIn(name, isMember) {
      paint(
        "<h3>" + (isMember ? "Diamond member" : "Signed in" +
          (name ? " as " + esc(name) : "")) + "</h3>" +
        (isMember
          ? "<p>Membership active." +
            (gated ? "" : " Everything is open to all readers during the preview.") + "</p>"
          : gated
            ? "<p>Diamond is live" + (price != null ? " at $" + esc(price) + " a month" : "") + ".</p>"
            : "<p>Nothing is gated during the preview." +
              (founding != null
                ? " At launch, founding members pay $" + esc(founding) + " a month, held for a year."
                : "") + "</p>") +
        '<p class="dm-fine">Diamond funds the free site.</p>'
      );
    }

    A.ready().then(function () {
      function sync() {
        var signed = A.isSignedIn && A.isSignedIn();
        if (!signed) { signedOut(); return; }
        var prof = (A.profile && A.profile()) || null;
        signedIn(prof && prof.username, !!(A.isDiamond && A.isDiamond()));
      }
      sync();
      if (A.onAuthChange) A.onAuthChange(sync);
    }).catch(signedOut);
  }

  // ---- boot -----------------------------------------------------------------
  // LOAD ORDER MATTERS HERE. page() emits the account layer at the END of the
  // body, after this file's <script>. All of them are deferred, and deferred
  // scripts run in document order AFTER parsing, so at the moment this IIFE
  // executes document.readyState is already "interactive" and
  // window.EephusAccount does NOT exist yet. Reading it right here would have
  // rendered the logged-out call to action for a signed-in member, every time.
  //
  // The fetches can start immediately (the mount points are parsed by now).
  // Only the account-dependent part waits for DOMContentLoaded, which fires
  // after every deferred script including eephus-account.js.
  function afterScripts(fn) {
    if (document.readyState === "complete") fn();
    else document.addEventListener("DOMContentLoaded", fn, { once: true });
  }
  function boot() {
    getJSON(SCOREBOARD_URL).then(renderReceipts).catch(function (e) {
      receiptsFailed(String((e && e.message) || e));
    });
    loadRecord();
    afterScripts(renderCTA);
  }
  boot();

  // ---- module styles --------------------------------------------------------
  // Injected rather than added to site.css: this is one page's worth of rules
  // and site.css is shared by every surface. Theme tokens only, sharp corners,
  // and every value carries a fallback so an unthemed render is still legible.
  //
  // TOKEN NAMES ARE CHECKED, NOT GUESSED (fixed 2026-08-05, first real-browser
  // render). This sheet was written against `--border-subtle`, which THIS SITE
  // DOES NOT DEFINE: getPropertyValue("--border-subtle") is "" in both themes,
  // so every rule below fell through to its hardcoded #333 / #222 fallback.
  // In dark that was near enough to pass unnoticed. In LIGHT it painted a
  // near-black 1px rule around every card, tile, stat box and table row on a
  // cream page, where the real token --border is #C9C1AE. The tell was that
  // the SAME cards looked correct with JavaScript off, because site.css's own
  // .card rule uses --border and this sheet was overriding it with a worse
  // value. Tokens used here now: --border (hairline), --border-light (the
  // softer inner rule), both defined in site.css for light and dark.
  //
  // The fine print also has to out-specify site.css's `.card p` (0,1,1), which
  // otherwise sets it to .95rem and --text-secondary: the provenance line, the
  // protocol line and the "Diamond funds the free site" line were all rendering
  // at body size, so the page had no fine print, only more body copy.
  var css = document.createElement("style");
  css.textContent = [
    ".diamond-app .card{border:1px solid var(--border,#c9c1ae);background:var(--bg-secondary);padding:14px 16px;margin:12px 0}",
    ".diamond-app .diamond-banner{border-left:3px solid var(--accent-cyan,#2a7)}",
    ".diamond-app .diamond-price h3{margin-top:0}",
    ".diamond-fine,.dm-fine{font-size:12px;color:var(--text-tertiary);margin-top:8px}",
    ".diamond-app .card p.diamond-fine,.diamond-app .card p.dm-fine," +
      ".diamond-app p.diamond-fine,.diamond-app p.dm-fine" +
      "{font-size:12px;line-height:1.5;color:var(--text-tertiary)}",
    ".dm-tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:12px;margin:12px 0}",
    ".dm-tile{border:1px solid var(--border,#c9c1ae);padding:10px 12px;background:var(--bg-primary,transparent)}",
    ".dm-tile-lbl{font:600 11px/1.3 var(--font-retro,monospace);color:var(--text-tertiary);text-transform:uppercase;letter-spacing:.04em;margin-bottom:8px}",
    ".dm-tile-row{display:flex;justify-content:space-between;align-items:baseline;gap:10px;padding:2px 0}",
    ".dm-tile-who{font-size:12.5px;color:var(--text-secondary)}",
    ".dm-tile-val{font:700 16px/1 var(--font-retro,monospace);color:var(--text-primary)}",
    ".dm-tile-val.dm-ours{color:var(--accent-green,#3a9)}",
    ".dm-tile-n{font-size:11px;color:var(--text-tertiary);margin-top:6px}",
    ".dm-table{width:100%;border-collapse:collapse;font-size:13px;margin:10px 0}",
    ".dm-table th{text-align:right;font:600 11px/1 var(--font-retro,monospace);color:var(--text-tertiary);text-transform:uppercase;letter-spacing:.03em;padding:6px 8px;border-bottom:1px solid var(--border,#c9c1ae)}",
    ".dm-table th:first-child{text-align:left}",
    ".dm-table td{padding:6px 8px;border-bottom:1px solid var(--border-light,var(--border,#e2dcc9));color:var(--text-primary)}",
    ".dm-table td.dm-num{text-align:right;font-variant-numeric:tabular-nums}",
    ".dm-table td.dm-win{color:var(--accent-green,#3a9);font-weight:700}",
    ".dm-stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:8px;margin:10px 0}",
    ".dm-stat{border:1px solid var(--border,#c9c1ae);padding:8px 10px;display:flex;flex-direction:column;gap:3px}",
    ".dm-stat-lbl{font:600 10px/1.2 var(--font-retro,monospace);color:var(--text-tertiary);text-transform:uppercase;letter-spacing:.04em}",
    ".dm-stat-val{font:700 15px/1 var(--font-retro,monospace);color:var(--text-primary)}",
    ".dm-btn{font:600 13px/1 var(--font-retro,monospace);padding:9px 14px;border:1px solid var(--accent-cyan,#2a7);background:transparent;color:var(--accent-cyan,#2a7);cursor:pointer;margin-top:6px}",
    ".dm-btn:hover{background:var(--bg-hover,transparent)}",
    ".dm-btn[disabled]{opacity:.6;cursor:default}",
    ".diamond-app .article-grid{margin-bottom:4px}"
  ].join("");
  document.head.appendChild(css);
})();
