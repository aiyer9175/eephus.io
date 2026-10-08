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
//   1. filter the already-rendered rows by verdict or audit flag,
//   2. re-derive each artifact age against the READER's clock rather than the
//      build clock, so a page served from a cache for a week stops claiming the
//      freshness it had on the day it was built,
//   3. move the rendered rows between the verdict groups and the family groups
//      when the reader changes the grouping (LIBRARY_7).
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
  var each = function (list, fn) { Array.prototype.forEach.call(list, fn); };

  // ---- group by verdict or by family (LIBRARY_7) ----------------------------
  // The rows render once, inside their verdict groups. The family groups are
  // rendered empty with their counts (.acct-fam, hidden); picking Family moves
  // each row into its family's group in page order, and Verdict moves it home.
  var groups = app.querySelectorAll(".acct-group");
  var fams = app.querySelectorAll(".acct-fam");
  var famBy = {};
  each(fams, function (f) { famBy[f.getAttribute("data-acct-fam")] = f; });
  var rows = [];
  each(groups, function (g) {
    each(g.querySelectorAll(".acct-row"), function (r) {
      rows.push({ el: r, home: g, v: g.getAttribute("data-acct-group"),
                  fam: r.getAttribute("data-fam") });
    });
  });
  var gbs = app.querySelectorAll("[data-acct-groupby]");
  var S = { key: "all", by: "verdict", anchor: null };

  function flagged(r, key) {
    return (" " + (r.getAttribute("data-acct-flags") || "") + " ").indexOf(" " + key + " ") !== -1;
  }

  // The hash is the shareable address of a filtered view: a link to the loss
  // ledger has to survive being pasted somewhere.
  function writeHash() {
    var parts = [];
    if (S.by === "family") parts.push(S.anchor ? "family=" + S.anchor : "group=family");
    if (S.key !== "all") parts.push((VERDICTS[S.key] ? "verdict=" : "show=") + S.key);
    try {
      history.replaceState(null, "", parts.length ? "#" + parts.join("&") : location.pathname);
    } catch (err) { /* file:// and sandboxed frames refuse replaceState */ }
  }

  function apply(key) {
    S.key = key;
    var byFlag = key !== "all" && !VERDICTS[key];
    if (S.by === "family") {
      // Under the family grouping a verdict chip cuts across the groups too.
      var shown = {};
      rows.forEach(function (o) {
        var on = key === "all" || (byFlag ? flagged(o.el, key) : o.v === key);
        o.el.style.display = on ? "" : "none";
        if (on) shown[o.fam] = (shown[o.fam] || 0) + 1;
      });
      each(fams, function (f) {
        f.style.display = shown[f.getAttribute("data-acct-fam")] ? "" : "none";
      });
    } else {
      each(groups, function (g) {
        var n = 0;
        each(g.querySelectorAll(".acct-row"), function (r) {
          var on = !byFlag || flagged(r, key);
          r.style.display = on ? "" : "none";
          if (on) n++;
        });
        var groupOn = byFlag
          ? n > 0
          : (key === "all" || g.getAttribute("data-acct-group") === key);
        g.style.display = groupOn ? "" : "none";
      });
    }
    each(chips, function (c) {
      c.classList.toggle("active", c.getAttribute("data-acct-filter") === key);
    });
    writeHash();
  }

  function groupBy(by) {
    S.by = by === "family" ? "family" : "verdict";
    rows.forEach(function (o) {
      var box = S.by === "family" ? famBy[o.fam] : o.home;
      if (box) box.appendChild(o.el);
    });
    each(groups, function (g) { g.hidden = S.by === "family"; });
    each(fams, function (f) { f.hidden = S.by !== "family"; });
    each(gbs, function (b) {
      var on = b.getAttribute("data-acct-groupby") === S.by;
      b.classList.toggle("active", on);
      b.setAttribute("aria-pressed", on ? "true" : "false");
    });
    apply(S.key);
  }

  each(chips, function (c) {
    c.addEventListener("click", function () {
      S.anchor = null;
      apply(c.getAttribute("data-acct-filter"));
    });
  });
  each(gbs, function (b) {
    b.addEventListener("click", function () {
      S.anchor = null;
      groupBy(b.getAttribute("data-acct-groupby"));
    });
  });

  // #verdict= / #show= pick a filter; #group=family or #family=<id> (the
  // Library's old view address forwards here with one) pick the grouping.
  var h = location.hash || "";
  var m = /(?:^|[#&])(?:verdict|show)=([a-z]+)/.exec(h);
  var fm = /(?:^|[#&])family=([a-z0-9-]+)/.exec(h);
  var gm = /(?:^|[#&])group=family(?:&|$)/.exec(h);
  if (m && app.querySelector('[data-acct-filter="' + m[1] + '"]')) S.key = m[1];
  if (fm && famBy[fm[1]]) S.anchor = fm[1];
  if (S.anchor || gm) {
    groupBy("family");
    if (S.anchor && famBy[S.anchor].scrollIntoView) famBy[S.anchor].scrollIntoView({ block: "start" });
  } else if (S.key !== "all") {
    apply(S.key);
  }
})();
