// Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
// Unauthorized copying of this file, via any medium is strictly prohibited
// Proprietary and confidential
// Written by Noah J. Dengler (@ARKNDJL), 2026

// /models/updates/ - the Model Updates client (LIBRARY_12).
//
// DELIBERATELY THIN, on the /models/ precedent. It renders no number and
// fetches nothing: every row, edge text, interval and ladder on the page is
// server-rendered by build_site.build_model_updates(), so the page is complete
// with JavaScript off. All this client does is:
//
//   1. open and close the per-model drawers (a #model=<id> address opens one),
//   2. filter the timetable rows already in the DOM (family, change kind, the
//      three layer toggles, a search over model names),
//   3. re-derive each "last update" age against the READER's clock.
(function () {
  "use strict";

  var app = document.querySelector(".mu-app");
  if (!app) return;
  var ST = window.EephusState;

  // ---- ages against the reader's clock ------------------------------------
  var DAY = 86400000;
  Array.prototype.forEach.call(app.querySelectorAll("time[datetime] + .mu-age"), function (el) {
    var iso = el.previousElementSibling.getAttribute("datetime");
    var when = Date.parse(iso + "T00:00:00");
    if (isNaN(when)) return;
    var days = Math.floor((Date.now() - when) / DAY);
    if (days >= 0) el.textContent = days + "d";
  });

  // ---- drawers -------------------------------------------------------------
  function setOpen(btn, open) {
    var d = document.getElementById(btn.getAttribute("aria-controls"));
    if (!d) return;
    d.hidden = !open;
    btn.setAttribute("aria-expanded", open ? "true" : "false");
  }
  app.addEventListener("click", function (e) {
    var btn = e.target.closest ? e.target.closest(".mu-open") : null;
    if (!btn) return;
    var open = btn.getAttribute("aria-expanded") !== "true";
    setOpen(btn, open);
    var row = btn.closest("tr");
    try {
      history.replaceState(null, "", open && row ? "#" + row.id : location.pathname);
    } catch (err) { /* file:// and sandboxed frames refuse replaceState */ }
  });
  function openFromHash() {
    var m = /(?:^|[#&])model=([A-Za-z0-9_.-]+)/.exec(location.hash || "");
    if (!m) return;
    var row = document.getElementById("model=" + m[1]);
    if (!row) return;
    var fold = row.closest("details");
    if (fold) fold.open = true;
    var btn = row.querySelector(".mu-open");
    if (btn) setOpen(btn, true);
    row.scrollIntoView({ block: "start" });
    if (btn) btn.focus({ preventScroll: true });
  }
  window.addEventListener("hashchange", openFromHash);
  openFromHash();

  // ---- timetable filters -----------------------------------------------------
  var rows = Array.prototype.slice.call(app.querySelectorAll("#mu-rows > tr"));
  var status = document.getElementById("mu-status");
  var empty = document.getElementById("mu-empty");
  var q = document.getElementById("mu-q");
  var total = rows.length;
  var S = { fam: "all", kind: "all", layers: {}, q: "" };

  function label(attr, key) {
    var b = app.querySelector("[" + attr + '="' + key + '"]');
    return b ? b.textContent.replace(/\s+\d+$/, "") : key;
  }
  // The search reads the Model cell's own text (the name a reader sees).
  var names = [];
  function nameOf(r) {
    var i = rows.indexOf(r);
    if (names[i] == null) names[i] = (r.cells[1] ? r.cells[1].textContent : "").toLowerCase();
    return names[i];
  }
  function apply() {
    var shown = 0;
    rows.forEach(function (r) {
      var lay = r.getAttribute("data-l") || "headline";
      var served = r.getAttribute("data-s") !== "0";
      var layerOn = lay === "headline" || lay === "secondary" || lay === "note" || !!S.layers[lay];
      var on = layerOn && (served || !!S.layers.development) &&
        (S.fam === "all" || r.getAttribute("data-f") === S.fam) &&
        (S.kind === "all" || r.getAttribute("data-k") === S.kind) &&
        (!S.q || nameOf(r).indexOf(S.q) !== -1);
      r.hidden = !on;
      if (on) shown++;
    });
    if (status) status.textContent = "Showing " + shown + " of " + total + " updates.";
    if (empty) {
      if (shown) {
        empty.innerHTML = "";
      } else {
        var esc = function (s) { return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;"); };
        var msg = "No updates match " + esc(label("data-mu-fam", S.fam)) + " and " +
          esc(label("data-mu-kind", S.kind)) + (S.q ? ' and "' + esc(S.q) + '"' : "") + ".";
        if (ST) ST.render(empty, "empty", msg, "mu-empty-state");
        else empty.textContent = msg;
      }
    }
  }
  function press(attr, key) {
    Array.prototype.forEach.call(app.querySelectorAll("[" + attr + "]"), function (b) {
      var on = b.getAttribute(attr) === key;
      b.classList.toggle("active", on);
      b.setAttribute("aria-pressed", on ? "true" : "false");
    });
  }
  function setLayer(lay, on) {
    S.layers[lay] = on;
    var b = app.querySelector('[data-mu-layer="' + lay + '"]');
    if (b) {
      b.setAttribute("aria-pressed", on ? "true" : "false");
      b.classList.toggle("active", on);
    }
  }
  app.addEventListener("click", function (e) {
    var b = e.target.closest ? e.target.closest("[data-mu-fam],[data-mu-kind],[data-mu-layer]") : null;
    if (!b) return;
    if (b.hasAttribute("data-mu-fam")) {
      S.fam = b.getAttribute("data-mu-fam");
      press("data-mu-fam", S.fam);
    } else if (b.hasAttribute("data-mu-kind")) {
      S.kind = b.getAttribute("data-mu-kind");
      press("data-mu-kind", S.kind);
      // A registration is its own layer: the chip turns its toggle on.
      if (S.kind === "registered") setLayer("registration", true);
    } else {
      var lay = b.getAttribute("data-mu-layer");
      setLayer(lay, b.getAttribute("aria-pressed") !== "true");
    }
    apply();
  });

  // The search waits for typing to pause; the pixel loading state stands in
  // the empty slot while it does (the only loading this page has).
  var timer = null;
  if (q) {
    q.addEventListener("input", function () {
      if (timer) clearTimeout(timer);
      if (ST && empty) ST.render(empty, "loading", "Filtering updates", "mu-wait");
      timer = setTimeout(function () {
        timer = null;
        S.q = q.value.trim().toLowerCase();
        apply();
      }, 180);
    });
  }

  // ---- the filter drawer at phone width -------------------------------------
  var fbtn = app.querySelector(".mu-filter-btn");
  var bar = document.getElementById("mu-bar");
  if (fbtn && bar) {
    fbtn.addEventListener("click", function () {
      var open = fbtn.getAttribute("aria-expanded") !== "true";
      fbtn.setAttribute("aria-expanded", open ? "true" : "false");
      bar.classList.toggle("is-open", open);
    });
  }
  app.classList.add("mu-live");
})();
