/* Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
 * Unauthorized copying of this file, via any medium is strictly prohibited
 * Proprietary and confidential
 * Written by Noah J. Dengler (@ARKNDJL), 2026 */

// =============================================================================
// eephus.io - primary-nav "MLB Modules" dropdown enhancer + phone hamburger
// =============================================================================
// The grouped nav uses a native <details class="eephus-nav-group">, so it
// toggles and is keyboard-accessible (Tab to the summary, Enter/Space to open)
// with zero JS. This adds niceties on top of the native behavior:
//   1. DESKTOP ONLY: the menu is position:fixed and placed under its summary at
//      open time, so it escapes the nav bar's horizontal-scroll overflow clip;
//      on phones (<=640px) the menu renders inline (static) inside the open
//      nav panel, so no placement happens there;
//   2. opening one group closes any other open group;
//   3. an outside click or the Escape key closes any open group;
//   4. PHONES (<=640px): a hamburger toggle is injected into the nav bar; the
//      link strip is hidden until the toggle opens it as a vertical panel
//      ([data-nav-open] on the header). Esc / outside click close it, and
//      resizing across the breakpoint resets the state.
// Idempotent and dependency-free; safe to load on pages with no group nav.
(function () {
  "use strict";
  if (window.__eephusNavGroup) return;
  window.__eephusNavGroup = true;

  // Phone breakpoint - matches site.css's <=640px nav collapse.
  var mqPhone = window.matchMedia ? window.matchMedia("(max-width: 640px)") : null;
  function isPhone() { return !!(mqPhone && mqPhone.matches); }

  function openGroups() {
    return document.querySelectorAll("details.eephus-nav-group[open]");
  }

  function place(d) {
    var s = d.querySelector("summary");
    var m = d.querySelector(".eephus-nav-menu");
    if (!s || !m) return;
    if (isPhone()) {
      // Inline (static) inside the mobile panel - clear any stale fixed coords.
      m.style.left = "";
      m.style.top = "";
      return;
    }
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
  window.addEventListener("resize", function () { reposition(); syncSubToggles(); });
  window.addEventListener("scroll", reposition, true);

  // ---- phone module subtitle: tap to expand (<=640px) ------------------------
  // site.css clamps .section-head .section-sub to 2 lines on phones. The old
  // mitigation put the full text in a `title` attribute, which is a HOVER
  // tooltip: on the one device class where the clamp fires, that affordance
  // does not exist. Measured 2026-08-07 at 390px, 5 of 7 lines hidden on the
  // since-retired /cards/ screen, 6 of 8 on /mlbstats/, 7 of 9 on /pal/ - and
  // the hidden run there was the module's own disclaimer. So the
  // clamp now hangs off [data-sub-collapsed] and comes with a real button.
  var subSeq = 0;

  function subToggleOf(el) {
    var b = el.nextElementSibling;
    return (b && b.classList && b.classList.contains("section-sub-toggle")) ? b : null;
  }

  function setSubOpen(el, open) {
    if (open) el.removeAttribute("data-sub-collapsed");
    else el.setAttribute("data-sub-collapsed", "");
    var b = subToggleOf(el);
    if (b) {
      b.setAttribute("aria-expanded", open ? "true" : "false");
      b.textContent = open ? "Show less" : "Read more";
    }
  }

  function ensureSubToggle(el) {
    var b = subToggleOf(el);
    if (b) return b;                       // idempotent
    if (!el.id) el.id = "section-sub-" + (++subSeq);
    b = document.createElement("button");
    b.type = "button";
    b.className = "section-sub-toggle";
    b.setAttribute("aria-controls", el.id);
    b.setAttribute("aria-expanded", "false");
    b.textContent = "Read more";
    b.addEventListener("click", function () {
      setSubOpen(el, el.hasAttribute("data-sub-collapsed"));
    });
    el.insertAdjacentElement("afterend", b);
    return b;
  }

  // Show the control only where it buys something. The clamp is a phone-width
  // rule, so overflow is measured in the collapsed state at the CURRENT width
  // and re-measured on resize: a subtitle that already fits in two lines (the
  // FA masthead, measured) never grows a button, and one that only overflows
  // at 390px gains it when the window gets there.
  function syncSubToggles() {
    document.querySelectorAll(".section-head .section-sub").forEach(function (el) {
      var b = ensureSubToggle(el);
      // An expanded subtitle was only expandable because it overflowed, so it
      // keeps its control (now reading "Show less") without re-measuring.
      var overflows = el.hasAttribute("data-sub-collapsed")
        ? el.scrollHeight - el.clientHeight > 1
        : true;
      b.classList.toggle("is-needed", overflows);
    });
  }
  // The measurement above depends on the face the text is set in. Since
  // 2026-09-03 PixelMplus12 leads the copy stack on every platform, so the
  // first paint uses the swap-in system face and the webfont lands later with
  // wider glyphs: a subtitle that fit its two lines at load can overflow after
  // the swap (fa/ at 390px hid 19px with a control that had already been judged
  // unnecessary). Re-measure when the fonts settle and on any later font load.
  if (document.fonts && typeof document.fonts.addEventListener === "function") {
    if (document.fonts.ready && typeof document.fonts.ready.then === "function") {
      document.fonts.ready.then(syncSubToggles);
    }
    document.fonts.addEventListener("loadingdone", syncSubToggles);
  }

  // ---- phone hamburger (<=640px) --------------------------------------------
  function navHeader() { return document.querySelector("header.eephus-nav"); }
  function navToggleBtn(h) { return h ? h.querySelector(".eephus-nav-toggle") : null; }

  function setNavOpen(h, open) {
    if (!h) return;
    if (open) h.setAttribute("data-nav-open", "");
    else h.removeAttribute("data-nav-open");
    var b = navToggleBtn(h);
    if (b) {
      b.setAttribute("aria-expanded", open ? "true" : "false");
      b.setAttribute("aria-label", open ? "Close navigation menu" : "Open navigation menu");
    }
    // Closing the panel also folds any open dropdown group inside it.
    if (!open) openGroups().forEach(function (d) { d.removeAttribute("open"); });
  }

  function ensureNavToggle() {
    var h = navHeader();
    if (!h || navToggleBtn(h)) return;   // idempotent
    var links = h.querySelector(".eephus-links");
    if (!links) return;
    if (!links.id) links.id = "eephus-nav-links";
    var b = document.createElement("button");
    b.type = "button";
    b.className = "eephus-nav-toggle";
    b.setAttribute("aria-controls", links.id);
    b.setAttribute("aria-expanded", "false");
    b.setAttribute("aria-label", "Open navigation menu");
    b.innerHTML = '<span aria-hidden="true">☰</span>';
    b.addEventListener("click", function () {
      setNavOpen(h, !h.hasAttribute("data-nav-open"));
    });
    h.appendChild(b);
  }

  // Crossing the breakpoint resets state: leaving phone widths closes the
  // panel (desktop shows the horizontal strip); entering them clears any
  // fixed dropdown coords via place()'s phone guard.
  function onBreakpointChange() {
    if (!isPhone()) setNavOpen(navHeader(), false);
    reposition();
    syncSubToggles();
  }
  if (mqPhone) {
    if (mqPhone.addEventListener) mqPhone.addEventListener("change", onBreakpointChange);
    else if (mqPhone.addListener) mqPhone.addListener(onBreakpointChange);
  }

  document.addEventListener("click", function (e) {
    openGroups().forEach(function (d) {
      if (!d.contains(e.target)) d.removeAttribute("open");
    });
    var h = navHeader();
    if (h && h.hasAttribute("data-nav-open") && !h.contains(e.target)) {
      setNavOpen(h, false);
    }
  });

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" || e.key === "Esc") {
      openGroups().forEach(function (d) { d.removeAttribute("open"); });
      var h = navHeader();
      if (h && h.hasAttribute("data-nav-open")) {
        setNavOpen(h, false);
        var b = navToggleBtn(h);
        if (b) b.focus();
      }
    }
  });

  function init() {
    ensureNavToggle();
    // Collapse first (that is what arms the CSS clamp), then measure. The
    // `title`-attribute mitigation this replaced is deliberately NOT kept: a
    // hover tooltip duplicating text the desktop already shows in full is
    // noise, and it was never reachable on the phone widths that clamp.
    document.querySelectorAll(".section-head .section-sub").forEach(function (el) {
      setSubOpen(el, false);
    });
    syncSubToggles();
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
