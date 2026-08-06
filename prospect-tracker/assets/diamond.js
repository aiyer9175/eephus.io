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
//   2. THE BETTING RECORD. Reads data/betting_record.json. While that file
//      does not exist (no picks posted yet) the card says the record starts
//      when the picks do, which is the truth, instead of hiding the section.
//   3. A SIGN-IN AWARE CALL TO ACTION, via the existing account layer.
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
  function card(inner) { return '<div class="card diamond-card">' + inner + "</div>"; }
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

  function getJSON(url) {
    return fetch(url, { cache: "no-cache" }).then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    });
  }

  // ---- 1. model receipts ----------------------------------------------------
  // Shape read (data/xfv_scoreboard_eval.json, written by the eFV scoreboard
  // eval): head_to_head.vs.<source>.{spearman,auc_contributor} each carrying
  // {n, efv, consensus, win, margin}. Anything absent is skipped rather than
  // faked, so an artifact that changes shape degrades to fewer tiles.
  function tile(label, ours, theirs, n, sub) {
    var a = dec(ours), b = dec(theirs);
    if (a == null || b == null) return "";
    return '<div class="dm-tile">' +
      '<div class="dm-tile-lbl">' + esc(label) + "</div>" +
      '<div class="dm-tile-row"><span class="dm-tile-who">eFV</span>' +
        '<span class="dm-tile-val dm-ours">' + esc(a) + "</span></div>" +
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
      root.innerHTML = note(
        "The model scoreboard artifact is here but does not carry a head to head block. " +
        "Nothing is being claimed until it does.");
      return;
    }
    var who = against.label || "the public consensus";
    var sp = against.spearman || {};
    var auc = against.auc_contributor || {};
    var tiles =
      tile("Rank correlation with realized career WAR", sp.efv, sp.consensus, sp.n, who) +
      tile("Picking out the players who became contributors", auc.efv, auc.consensus, auc.n, who);
    if (!tiles) {
      root.innerHTML = note("The scoreboard artifact carries no comparable metrics yet.");
      return;
    }
    var arch = (h2h.by_archetype_vs_consensus || []).filter(function (a) {
      return a && a.spearman && a.spearman.efv != null;
    });
    var archHTML = "";
    if (arch.length) {
      // SAY WHICH METRIC. The table reads by_archetype_vs_consensus[].spearman
      // and nothing else, but it sits directly under two tiles carrying two
      // DIFFERENT numbers (rank correlation and contributor AUC) and named
      // neither of them. A reader had no way to tell which one the per-group
      // rows were, and the green win highlight is a Spearman win specifically.
      archHTML = '<p class="dm-fine">Rank correlation with realized career ' +
        gl("WAR", "war") + ", by prospect group. Green is the higher of the two.</p>" +
        // The shared table dialect: .mlbstats-scroll + .mlbstats-table give the
        // sticky header, the frozen identity column and the horizontal scroller
        // this table never had, so the archetype rows cannot pan the page
        // sideways on a phone. .dm-table stays for the local colour rules.
        '<div class="mlbstats-scroll"><table class="dm-table mlbstats-table"><thead><tr>' +
        "<th>Group</th><th>" + gl("eFV", "xfv") + "</th><th>" + esc(who) + "</th><th>n</th>" +
        "</tr></thead><tbody>" +
        arch.map(function (a) {
          var win = a.spearman.win ? " dm-win" : "";
          return "<tr><td>" + esc(a.label || a.archetype) + "</td>" +
            '<td class="dm-num' + win + '">' + esc(dec(a.spearman.efv)) + "</td>" +
            '<td class="dm-num">' + esc(dec(a.spearman.consensus)) + "</td>" +
            '<td class="dm-num">' + esc(commas(a.n)) + "</td></tr>";
        }).join("") +
        "</tbody></table></div>";
    }
    var protocol = h2h.protocol ? "<p class=\"dm-fine\">" + esc(h2h.protocol) + "</p>" : "";
    root.innerHTML = card(
      "<h3>The prospect model against the public consensus</h3>" +
      "<p>Both numbers are scored on the same players, out of sample, in a forward-chained " +
      gl("backtest", "backtest") + ". " + gl("eFV", "xfv") + " never sees a player's own " +
      "outcome before it grades him. Higher is better in both rows.</p>" +
      '<div class="dm-tiles">' + tiles + "</div>" +
      archHTML +
      protocol +
      '<p class="dm-fine">Read live from data/xfv_scoreboard_eval.json on every page load. ' +
      "If the model slips, this card slips with it.</p>"
    );
    wireGl(root);
  }

  function receiptsFailed(msg) {
    var root = el("diamond-receipts");
    if (!root) return;
    root.innerHTML = note(
      "The model scoreboard did not load (" + (msg || "unknown error") + "). " +
      "The numbers live in data/xfv_scoreboard_eval.json and are published rather than typed in, " +
      "so this card stays empty rather than guessing.");
  }

  // ---- 2. betting record ----------------------------------------------------
  // data/betting_record.json is APPEND ONLY by design and is written by the
  // betting export. It does not exist until the first pick posts, and that is
  // a normal state, not an error: an absent file means no pick has ever been
  // published, which is exactly what the card should say.
  //
  // Key names are read tolerantly (summary block or top level, a couple of
  // spellings each) so this card does not become the reason a small rename in
  // the exporter breaks the pricing page.
  function pick(obj, names) {
    for (var i = 0; i < names.length; i++) {
      if (obj && obj[names[i]] != null) return obj[names[i]];
    }
    return null;
  }
  // Tolerate both 0.043 and 4.3 for a rate: anything inside [-1.5, 1.5] is read
  // as a fraction, which is how every other artifact on the site emits one.
  function asPct(v) {
    if (v == null || isNaN(v)) return null;
    var x = Number(v);
    return (x >= -1.5 && x <= 1.5) ? x * 100 : x;
  }
  // SIGNED, for quantities where the direction is the point: ROI and average
  // closing line value are returns, and "+7.1%" says something "7.1%" does not.
  function pctOf(v) {
    var x = asPct(v);
    return x == null ? null : (x >= 0 ? "+" : "") + x.toFixed(1) + "%";
  }
  // UNSIGNED, for a hit rate. "Beat the closing line +57.4%" reads as a change
  // in the rate; it is a share of picks, so it gets no sign.
  function ratePct(v) {
    var x = asPct(v);
    return x == null ? null : x.toFixed(1) + "%";
  }
  function statRow(label, value) {
    if (value == null || value === "") return "";
    return '<div class="dm-stat"><span class="dm-stat-lbl">' + esc(label) + "</span>" +
      '<span class="dm-stat-val">' + esc(value) + "</span></div>";
  }
  function emptyRecord(reason) {
    var root = el("diamond-betting-record");
    if (!root) return;
    root.innerHTML = card(
      "<h3>The betting record starts when the picks do</h3>" +
      "<p>No pick has been published yet, so there is nothing to grade. When picks start, every one of " +
      "them lands here with its timestamp, its book, the odds it was posted at, and a flat one unit " +
      "stake. The file is append only: a losing pick cannot be edited out of it later.</p>" +
      "<p>Each pick is also graded against the closing line. Win rate flatters a lucky month. Beating " +
      "the close is the part that is hard to fake.</p>" +
      (reason ? '<p class="dm-fine">' + esc(reason) + "</p>" : "")
    );
  }
  // POSTED IS NOT THE SAME AS GRADED, and the guard below used to say one
  // sentence for both. A record file carrying picks that have not settled yet
  // has no wins and no losses, so it fell into emptyRecord and the page said
  // "no pick has been published yet" on a page whose own file listed picks.
  // That is a false statement about our own record, on the page that asks for
  // money on the strength of that record being honest.
  function ungradedRecord(nPosted, asof) {
    var root = el("diamond-betting-record");
    if (!root) return;
    root.innerHTML = card(
      "<h3>" + esc(nPosted) + " pick" + (nPosted === 1 ? " is" : "s are") +
        " posted and none has settled</h3>" +
      "<p>The record file is live and carries " + esc(nPosted) + " pick" +
        (nPosted === 1 ? "" : "s") + ", each with its timestamp, its book, the odds it was " +
        "posted at and a flat one unit stake. None of them has a result yet, so there is no " +
        "record to report: a win rate over zero graded picks is not a number.</p>" +
      "<p>Every pick is also graded against the closing line once it settles. Win rate flatters " +
      "a lucky month. Beating the close is the part that is hard to fake.</p>" +
      (asof ? '<p class="dm-fine">Record as of ' + esc(String(asof).slice(0, 10)) + ".</p>" : "")
    );
  }
  function renderRecord(doc) {
    var s = (doc && (doc.summary || doc.totals)) || doc || {};
    var picks = (doc && doc.picks) || [];
    var n = pick(s, ["n_picks", "n", "graded", "count"]);
    if (n == null && picks.length) n = picks.length;
    var w = pick(s, ["wins", "w", "won"]);
    var l = pick(s, ["losses", "l", "lost"]);
    var asofEarly = pick(doc || {}, ["generated_at", "as_of", "updated_at"]);
    // Three states, three messages. Nothing posted; posted but nothing settled;
    // and a real graded record. The middle one used to be told the first one's
    // sentence, which was a claim about our own file that the file contradicts.
    var nPosted = (n != null && n) ? n : picks.length;
    if (!nPosted) { emptyRecord(""); return; }
    if (w == null && l == null) { ungradedRecord(nPosted, asofEarly); return; }
    var p = pick(s, ["pushes", "push", "void", "voids"]);
    var units = pick(s, ["net_units", "units", "profit_units"]);
    var roi = pick(s, ["roi", "roi_pct"]);
    var clv = pick(s, ["avg_clv", "clv_avg", "avg_clv_pct"]);
    var beat = pick(s, ["beat_close_rate", "beat_close", "clv_win_rate"]);
    var asof = pick(doc || {}, ["generated_at", "as_of", "updated_at"]);
    var root = el("diamond-betting-record");
    if (!root) return;
    root.innerHTML = card(
      "<h3>The betting record</h3>" +
      '<div class="dm-stats">' +
        statRow("Record", (w == null ? "0" : w) + " - " + (l == null ? "0" : l) +
                          (p ? " - " + p : "")) +
        statRow("Picks graded", commas(n)) +
        statRow("Net units", units == null ? null : (Number(units) >= 0 ? "+" : "") + Number(units).toFixed(2)) +
        statRow("ROI", pctOf(roi)) +
        statRow("Average closing line value", pctOf(clv)) +
        statRow("Beat the closing line", ratePct(beat)) +
      "</div>" +
      "<p>Flat one unit per pick. Nothing is removed after the fact. Closing line value is the honest " +
      "test: it says whether the number we posted was better than the number the market settled on.</p>" +
      (asof ? '<p class="dm-fine">Record as of ' + esc(String(asof).slice(0, 10)) + ".</p>" : "") +
      '<p class="dm-fine">21+. Informational and for entertainment only. Sports betting is not legal in ' +
      "every state. No affiliate links. If betting stops being fun, call 1-800-GAMBLER.</p>"
    );
  }

  // ---- 3. sign-in aware call to action -------------------------------------
  function renderCTA() {
    var root = el("diamond-cta");
    if (!root) return;
    var A = window.EephusAccount;
    var price = CFG.price_usd_month != null ? CFG.price_usd_month : 15;
    var founding = CFG.founding_rate_usd != null ? CFG.founding_rate_usd : 9.99;
    var gated = !!CFG.gating;

    function paint(html) { root.innerHTML = html; }
    function signedOut() {
      paint(
        "<h3>There is nothing to buy yet</h3>" +
        "<p>Diamond is " + (gated ? "live at $" + esc(price) + " a month" :
          "free during the founding preview. When it opens it is $" + esc(price) +
          " a month, or $" + esc(founding) + " for founding members") + ".</p>" +
        "<p>Make a free account so your watchlist, your bet log and your founding member status follow " +
        "you between devices.</p>" +
        '<button type="button" class="dm-btn" data-diamond="signin">Create a free account</button>'
      );
      var b = root.querySelector('[data-diamond="signin"]');
      if (b) {
        b.addEventListener("click", function () {
          if (window.EephusUI && window.EephusUI.openAuthModal) {
            window.EephusUI.openAuthModal("signin");
          } else {
            // The account layer is not configured on this build. Say so rather
            // than leaving a button that does nothing when clicked.
            b.disabled = true;
            b.textContent = "Accounts are not switched on yet";
          }
        });
      }
    }
    function signedIn(name, isMember) {
      paint(
        "<h3>" + (isMember ? "Thanks for keeping this free" : "You are signed in" +
          (name ? " as " + esc(name) : "")) + "</h3>" +
        (isMember
          ? "<p>Your Diamond membership is active. Everything in the Diamond section is open to you, " +
            "and it is open to everyone else too while the preview runs.</p>"
          : "<p>Nothing is gated during the preview, so there is nothing you need to do. When Diamond " +
            "opens, founding members pay $" + esc(founding) + " a month and keep that rate for a year.</p>") +
        '<p class="dm-fine">Diamond funds the free site.</p>'
      );
    }

    if (!A || !A.ready) { signedOut(); return; }
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
    getJSON(RECORD_URL).then(renderRecord).catch(function () {
      // 404 is the expected state before the first pick. Anything else lands
      // in the same honest card: there is no record to show.
      emptyRecord("");
    });
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
