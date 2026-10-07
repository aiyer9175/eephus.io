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
//   1. filter the already-rendered rows by verdict,
//   2. re-derive each artifact age against the READER's clock rather than the
//      build clock, so a page served from a cache for a week stops claiming the
//      freshness it had on the day it was built.
//
// (2) is the only thing here that can change a number on screen, and it can
// only ever move a number in the stale direction. The page's styles live in
// assets/accountability.css, linked by the page ahead of its markup (audit
// QREP05: injecting them from this deferred script moved the layout after
// first paint).
(function () {
  "use strict";

  var app = document.querySelector(".acct-app");
  if (!app) return;

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
      ? "stamped " + iso + "; past the " + bar + "-day stale bar"
      : "stamped " + iso;
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
