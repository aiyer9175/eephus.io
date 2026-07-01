/* Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
 * Unauthorized copying of this file, via any medium is strictly prohibited
 * Proprietary and confidential
 * Written by Noah J. Dengler (@ARKNDJL), 2026 */

// =============================================================================
// eephus.io - primary-nav "MLB Modules" dropdown enhancer
// =============================================================================
// The grouped nav uses a native <details class="eephus-nav-group">, so it
// toggles and is keyboard-accessible (Tab to the summary, Enter/Space to open)
// with zero JS. This adds three niceties on top of the native behavior:
//   1. the menu is position:fixed and placed under its summary at open time, so
//      it escapes the nav bar's horizontal-scroll overflow clip;
//   2. opening one group closes any other open group;
//   3. an outside click or the Escape key closes any open group.
// Idempotent and dependency-free; safe to load on pages with no group nav.
(function () {
  "use strict";
  if (window.__eephusNavGroup) return;
  window.__eephusNavGroup = true;

  function openGroups() {
    return document.querySelectorAll("details.eephus-nav-group[open]");
  }

  function place(d) {
    var s = d.querySelector("summary");
    var m = d.querySelector(".eephus-nav-menu");
    if (!s || !m) return;
    var r = s.getBoundingClientRect();
    m.style.left = Math.round(r.left) + "px";
    m.style.top = Math.round(r.bottom + 6) + "px";
  }

  // <details> fires a 'toggle' event on open/close; capture so we catch it.
  document.addEventListener("toggle", function (e) {
    var d = e.target;
    if (!d || !d.matches || !d.matches("details.eephus-nav-group")) return;
    if (d.open) {
      openGroups().forEach(function (o) { if (o !== d) o.removeAttribute("open"); });
      place(d);
    }
  }, true);

  function reposition() { openGroups().forEach(place); }
  window.addEventListener("resize", reposition);
  window.addEventListener("scroll", reposition, true);

  document.addEventListener("click", function (e) {
    openGroups().forEach(function (d) {
      if (!d.contains(e.target)) d.removeAttribute("open");
    });
  });

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" || e.key === "Esc") {
      openGroups().forEach(function (d) { d.removeAttribute("open"); });
    }
  });
})();
