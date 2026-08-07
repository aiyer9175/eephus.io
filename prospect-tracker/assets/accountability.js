// Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
// Unauthorized copying of this file, via any medium is strictly prohibited
// Proprietary and confidential
// Written by Noah J. Dengler (@ARKNDJL), 2026

// /models/ - the model accountability hub client.
//
// DELIBERATELY THIN. This file renders nothing and fetches nothing. Every row,
// verdict, count, date and link on that page is server-rendered by
// build_site.build_models() out of the model registry and out of the eval
// artifacts themselves, so the page is complete and honest with JavaScript
// switched off. (The registry path is deliberately not written out here: the
// SITE_MAP generator reads a payload filename in ANY asset file as a fetch this
// client makes, and it makes none.) All this client does is:
//
//   1. inject its own stylesheet (assets/site.css belongs to another lane, and
//      the /sources/ artifact cards set the precedent of styling a new surface
//      off the theme tokens instead of growing the shared sheet),
//   2. filter the already-rendered rows by verdict,
//   3. re-derive each artifact age against the READER's clock rather than the
//      build clock, so a page served from a cache for a week stops claiming the
//      freshness it had on the day it was built.
//
// (3) is the only thing here that can change a number on screen, and it can
// only ever move a number in the stale direction.
(function () {
  "use strict";

  var app = document.querySelector(".acct-app");
  if (!app) return;

  // ---- styles -------------------------------------------------------------
  // Tokens only, no literal colors: --accent-lilac carries the deprecated rows
  // because grey reads as "ignore this" and red reads as "something is broken",
  // and a measured no-ship is neither. Unvalidated takes --accent-orange, the
  // token the site already uses for "early", not the red it would earn if the
  // label meant defective. The page says what the labels mean in words too.
  var css = document.createElement("style");
  css.textContent = [
    ".acct-app .acct-intro{max-width:78ch;margin:14px 0 18px}",
    ".acct-app .acct-intro p{font-size:13px;line-height:1.6;color:var(--text-secondary);margin:0 0 10px}",
    ".acct-app .acct-intro code{font-family:var(--font-retro-mono);font-size:12px}",
    ".acct-app .acct-tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:10px;margin:0 0 22px}",
    ".acct-app .acct-tile{border:1px solid var(--border);border-top-width:3px;background:var(--bg-secondary);padding:12px 14px}",
    ".acct-app .acct-tilen{font:700 30px/1 var(--font-retro-mono);color:var(--text-primary)}",
    ".acct-app .acct-tilelab{font:700 10px/1.4 var(--font-retro-mono);letter-spacing:.12em;text-transform:uppercase;margin:8px 0 6px}",
    ".acct-app .acct-tiledef{font-size:11.5px;line-height:1.55;color:var(--text-tertiary)}",
    ".acct-app .acct-tile--validated{border-top-color:var(--accent-green)}",
    ".acct-app .acct-tile--validated .acct-tilelab{color:var(--accent-green)}",
    ".acct-app .acct-tile--provisional{border-top-color:var(--accent-gold)}",
    ".acct-app .acct-tile--provisional .acct-tilelab{color:var(--text-gold)}",
    ".acct-app .acct-tile--unvalidated{border-top-color:var(--accent-orange)}",
    ".acct-app .acct-tile--unvalidated .acct-tilelab{color:var(--accent-orange)}",
    ".acct-app .acct-tile--deprecated{border-top-color:var(--accent-lilac)}",
    ".acct-app .acct-tile--deprecated .acct-tilelab{color:var(--accent-lilac)}",
    ".acct-app .acct-note{margin:0 0 22px}",
    ".acct-app .acct-note h3{font-family:var(--font-retro-mono);font-size:13px;margin:0 0 8px}",
    ".acct-app .acct-list{margin:0;padding-left:18px}",
    ".acct-app .acct-list li{font-size:12.5px;line-height:1.65;color:var(--text-secondary);margin:0 0 6px}",
    ".acct-app .acct-orphans code{font-family:var(--font-retro-mono);font-size:11.5px}",
    ".acct-app .acct-filters{margin:0 0 14px}",
    ".acct-app .acct-count{font-family:var(--font-retro-mono);font-size:10px;color:var(--text-tertiary);margin-left:4px}",
    ".acct-app .acct-group{margin:0 0 26px}",
    ".acct-app .acct-grouphead{display:flex;align-items:baseline;gap:8px;border-bottom:1px solid var(--border);padding-bottom:5px}",
    ".acct-app .acct-grouptitle{font:700 13px/1 var(--font-retro-mono);letter-spacing:.08em;text-transform:uppercase;color:var(--text-primary)}",
    ".acct-app .acct-groupn{font:700 11px/1 var(--font-retro-mono);color:var(--text-tertiary)}",
    ".acct-app .acct-groupdef{font-size:11.5px;line-height:1.55;color:var(--text-tertiary);margin:7px 0 10px;max-width:78ch}",
    ".acct-app .acct-row{border-bottom:1px solid var(--border-light)}",
    // The open-row fields are a bare <dl> and the summary is bare code/b/i/time
    // elements: the ledger renders ~200 rows and a class attribute on every
    // element cost more markup than the prose it was labelling.
    ".acct-app .acct-sum{display:flex;align-items:center;gap:9px;flex-wrap:wrap;padding:7px 2px;cursor:pointer;list-style:none}",
    // display:flex on a <summary> drops the native disclosure marker in every
    // engine, so the row needs its own or nothing tells a reader it opens.
    ".acct-app .acct-sum::-webkit-details-marker{display:none}",
    '.acct-app .acct-sum::before{content:"\\25B8";font-size:10px;color:var(--text-tertiary);width:9px}',
    '.acct-app .acct-row[open]>.acct-sum::before{content:"\\25BE"}',
    ".acct-app .acct-sum:hover{background:var(--bg-hover)}",
    ".acct-app .acct-sum>code{font:700 12px/1.3 var(--font-retro-mono);color:var(--text-primary);word-break:break-word}",
    ".acct-app .acct-sum>i{font-size:11.5px;font-style:normal;color:var(--text-tertiary);flex:1 1 200px;min-width:0}",
    ".acct-app .acct-sum>time{font:700 10px/1 var(--font-retro-mono);color:var(--text-tertiary);white-space:nowrap}",
    ".acct-app .acct-sum>time:not([datetime]){font-style:italic;font-weight:400}",
    ".acct-app .acct-sum>time.is-stale{color:var(--accent-red)}",
    ".acct-app .acct-sum>b{font:700 8px/1.4 var(--font-retro-mono);letter-spacing:.1em;text-transform:uppercase;padding:2px 6px;border:1px solid var(--border);color:var(--text-tertiary);white-space:nowrap}",
    '.acct-app .acct-sum>b[data-v="validated"]{color:var(--accent-green);border-color:var(--accent-green)}',
    '.acct-app .acct-sum>b[data-v="provisional"]{color:var(--text-gold);border-color:var(--accent-gold)}',
    '.acct-app .acct-sum>b[data-v="unvalidated"]{color:var(--accent-orange);border-color:var(--accent-orange)}',
    '.acct-app .acct-sum>b[data-v="deprecated"]{color:var(--accent-lilac);border-color:var(--accent-lilac)}',
    ".acct-app .acct-body{display:grid;grid-template-columns:170px minmax(0,1fr);gap:4px 10px;margin:0;padding:4px 2px 14px}",
    ".acct-app .acct-body dt{font:700 9px/1.6 var(--font-retro-mono);letter-spacing:.09em;text-transform:uppercase;color:var(--text-tertiary)}",
    ".acct-app .acct-body dd{margin:0;font-size:12.5px;line-height:1.6;color:var(--text-secondary);overflow-wrap:anywhere}",
    ".acct-app .acct-body dd code{font-family:var(--font-retro-mono);font-size:11.5px}",
    ".acct-app .acct-nolink{font-style:italic;color:var(--text-tertiary)}",
    ".acct-app .acct-verbatim{font-family:var(--font-retro-mono);font-size:11.5px;line-height:1.6;color:var(--text-secondary)}",
    "@media (max-width:640px){.acct-app .acct-body{grid-template-columns:minmax(0,1fr);gap:2px}" +
      ".acct-app .acct-body dd{margin-bottom:8px}.acct-app .acct-sum>i{flex-basis:100%}}"
  ].join("");
  document.head.appendChild(css);

  // ---- age against the reader's clock -------------------------------------
  // Server-rendered ages are true as of the build. A CDN or a browser can hold
  // this page well past that, so each dated artifact carries its own ISO stamp
  // and the age is recomputed here. Anything unparseable is left exactly as the
  // server wrote it.
  var DAY = 86400000;
  var bar = parseInt(app.getAttribute("data-acct-stale-days"), 10);
  Array.prototype.forEach.call(app.querySelectorAll(".acct-sum>time[datetime]"), function (el) {
    var iso = el.getAttribute("datetime");
    var when = Date.parse(iso + "T00:00:00");
    if (isNaN(when)) return;
    var days = Math.floor((Date.now() - when) / DAY);
    if (days < 0) return;                       // a future stamp is not an age
    var stale = !isNaN(bar) && days > bar;
    el.textContent = days + "d";
    el.classList.toggle("is-stale", stale);
    el.title = stale
      ? "the artifact stamped itself " + iso + ", which is past the " + bar +
        "-day bar the pipeline calls stale"
      : "the artifact stamped itself " + iso;
  });

  // ---- filters ------------------------------------------------------------
  var chips = app.querySelectorAll("[data-acct-filter]");
  if (!chips.length) return;

  // Two kinds of chip. A verdict chip selects one of the rendered groups; an
  // audit chip (no eval artifact, artifact not published, undated, stale) cuts
  // ACROSS the groups, so it filters rows and then hides any group left empty.
  var VERDICTS = { validated: 1, provisional: 1, unvalidated: 1, deprecated: 1 };

  function apply(key) {
    var byFlag = key !== "all" && !VERDICTS[key];
    Array.prototype.forEach.call(app.querySelectorAll(".acct-group"), function (g) {
      var shown = 0;
      Array.prototype.forEach.call(g.querySelectorAll(".acct-row"), function (r) {
        var on = !byFlag ||
          (" " + (r.getAttribute("data-acct-flags") || "") + " ").indexOf(" " + key + " ") !== -1;
        r.style.display = on ? "" : "none";
        if (on) shown++;
      });
      var groupOn = byFlag
        ? shown > 0
        : (key === "all" || g.getAttribute("data-acct-group") === key);
      g.style.display = groupOn ? "" : "none";
    });
    Array.prototype.forEach.call(chips, function (c) {
      c.classList.toggle("active", c.getAttribute("data-acct-filter") === key);
    });
    // The hash is the shareable address of a filtered view: a link to the loss
    // ledger has to survive being pasted somewhere.
    try {
      history.replaceState(null, "", key === "all"
        ? location.pathname
        : "#" + (VERDICTS[key] ? "verdict=" : "show=") + key);
    } catch (err) { /* file:// and sandboxed frames refuse replaceState */ }
  }

  Array.prototype.forEach.call(chips, function (c) {
    c.addEventListener("click", function () {
      apply(c.getAttribute("data-acct-filter"));
    });
  });

  var m = /(?:^|[#&])(?:verdict|show)=([a-z]+)/.exec(location.hash || "");
  if (m && app.querySelector('[data-acct-filter="' + m[1] + '"]')) apply(m[1]);
})();
