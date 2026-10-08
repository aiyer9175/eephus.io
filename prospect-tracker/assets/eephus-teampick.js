/* Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
 * Unauthorized copying of this file, via any medium is strictly prohibited
 * Proprietary and confidential
 * Written by Noah J. Dengler (@ARKNDJL), 2026 */

// =============================================================================
// eephus.io team picker: team logos in every team dropdown
// =============================================================================
// Owner ask 2026-09-24: "add team logos to every dropdown menu that is
// team-based, similar to how we did with PROSPX". A native <select> cannot
// draw an image inside an option, so this upgrades one in place, the PROSPX
// org picker's look (chip trigger, searchable popover, logo + code + name
// rows) on top of the site's own select dialect.
//
// PROGRESSIVE, AND THE SELECT STAYS THE SOURCE OF TRUTH. Any
// <select data-team-picker> (value "mlb", the default, or "college") keeps
// living in the DOM: hidden, out of the tab order, still carrying the value,
// the options and the handlers its module wired. A trigger button is inserted
// just before it and a listbox panel opens at body level. Choosing a row sets
// select.value and dispatches bubbling "input" and "change" events, so every
// existing handler (addEventListener, an onchange property, an inline
// onchange attribute, a delegated listener) runs exactly as it did for a
// hand on the native control. Nothing in a module has to know this exists
// beyond the one attribute.
//
// THE MODULES REBUILD THEIR SELECTS. Most boards re-render by innerHTML, so
// the select a picker was built on is gone after every render. One
// MutationObserver over the body enhances each new select[data-team-picker]
// as it lands (in the same microtask, before paint), resyncs a picker when its
// option list or its style/hidden/disabled attributes change, and closes an
// open panel whose select has left the document. A module that sets
// select.value or selectedIndex in code (the Trade Board after its async
// options fill, the PROSPX chart filter on every render) is caught by an
// instance-level setter that resyncs the trigger.
//
// KEYBOARD AND READER. The trigger is a button with aria-haspopup=listbox,
// aria-expanded and a name built from the control's own label plus the
// current value. The panel is a search box over a role=listbox of
// role=option rows (aria-selected on the chosen one). Arrow keys, Home and
// End move; Enter or Space choose (Enter in an EMPTY search keeps the chosen
// value); typing on a row goes to the search box; Escape closes and returns
// focus to the trigger; Tab closes and moves on; an outside press closes. One panel is open at a time. A module that restores focus to its
// select after a re-render (MLB Stats does) lands on the trigger instead.
//
// LOGOS come from EEPHUS_HUB.club(), the one club table (both code families,
// OAK, FLA, MLBAM ids, full names). An <option data-logo="url"> overrides it,
// which is how the CollegeSavant schools that have a local logo carry one. A
// logo that fails to load is replaced by a text chip; a row that is not a
// club ("All teams", "Cuba", an overseas club) keeps its text beside a
// hollow diamond, the PROSPX "all" glyph.
(function () {
  "use strict";
  if (window.EephusTeamPick) return;

  var SEL = "select[data-team-picker]";
  var DIAMOND = "◇";
  var P_VALUE = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, "value");
  var P_INDEX = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, "selectedIndex");
  var openState = null;   // {inst, panel, search, list}
  var uid = 0;
  // The trigger that last held focus, and when. A module that re-renders
  // after a pick (at once, or again when a fetch lands) drops focus to the
  // body; the trigger that replaces this one takes it back.
  var lastFocus = { id: "", at: 0 };   // id = the trigger's data-teampick-key
  var FOCUS_FOLLOW_MS = 4000;

  function esc(s) {
    return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }
  function club(v) {
    var h = window.EEPHUS_HUB;
    try { return (h && h.club) ? h.club(v) : null; } catch (e) { return null; }
  }
  function isAllValue(v) { return v === "" || String(v).toLowerCase() === "all"; }
  function initials(text) {
    var w = String(text || "").replace(/[^A-Za-z0-9 ]+/g, " ").trim().split(/\s+/).filter(Boolean);
    if (!w.length) return "";
    if (w.length === 1) return w[0].slice(0, 3).toUpperCase();
    return w.slice(0, 3).map(function (x) { return x.charAt(0); }).join("").toUpperCase();
  }

  // ---- the option model -----------------------------------------------------
  // One row per <option>, in the select's own order (draft order, farm rank
  // and name sort are the modules' decisions and are kept).
  function model(sel, o) {
    var mode = sel.getAttribute("data-team-picker") || "mlb";
    var value = o.value, text = (o.textContent || "").trim();
    var c = (mode === "college" || isAllValue(value)) ? null : club(value);
    var logo = o.getAttribute("data-logo") || (c ? c.logo : "");
    var code = "", name = text, extra = "";
    if (c) {
      // The select's own spelling (CWS on MLB Stats, CHW on the prospect
      // side), because it is the spelling the table beside it prints.
      code = /^[A-Za-z]{2,3}$/.test(value) ? value.toUpperCase() : c.code;
      name = c.name;
      // Whatever the option text says beyond the code and the name (the farm
      // comparison's "(farm #3)") rides along, muted.
      var t = text;
      if (t.toUpperCase().indexOf(value.toUpperCase()) === 0) t = t.slice(value.length).trim();
      if (t.toLowerCase().indexOf(c.name.toLowerCase()) === 0) t = t.slice(c.name.length).trim();
      extra = t;
    }
    // A school (the college mode) that has no logo on disk still gets a mark:
    // its initials in a chip, so the diamond stays the sign of a non-team row.
    var school = mode === "college" && !isAllValue(value);
    var hay = [value, text, name].concat(c ? [c.code].concat(c.aliases) : []).join(" ").toLowerCase();
    return { value: value, text: text, club: c, school: school, logo: logo, code: code, name: name, extra: extra,
             fallback: c ? code : ((logo || school) ? initials(text) : ""), hay: hay, disabled: !!o.disabled };
  }

  // The mark sits inside the picker's own button or option, where no link may
  // go, so it is marked data-club-nolink="self" (owner ask 9: the club links
  // render test reads every MLB logo as a link or a named exception).
  function markHTML(m) {
    if (m.logo) {
      return '<img class="teampick-logo" src="' + esc(m.logo) + '" alt="" loading="lazy" decoding="async"'
        + ' data-fb="' + esc(m.fallback) + '" data-club-nolink="self">';
    }
    if (m.club || m.school) return '<span class="teampick-chip">' + esc(m.fallback) + "</span>";
    return '<span class="teampick-glyph" aria-hidden="true">' + DIAMOND + "</span>";
  }

  // A logo that 404s becomes a text chip (the code, or a school's initials).
  // One capture listener for every picker image: error events do not bubble.
  document.addEventListener("error", function (e) {
    var img = e.target;
    if (!img || img.tagName !== "IMG" || !img.classList.contains("teampick-logo")) return;
    var s = document.createElement("span");
    s.className = "teampick-chip";
    s.textContent = img.getAttribute("data-fb") || "";
    if (img.parentNode) img.parentNode.replaceChild(s, img);
  }, true);

  // ---- the label the control already has -----------------------------------
  function labelText(sel) {
    var a = sel.getAttribute("aria-label");
    if (a) return a.trim();
    var lab = sel.labels && sel.labels[0];
    if (lab) {
      var c = lab.cloneNode(true);
      Array.prototype.forEach.call(c.querySelectorAll("select, button, option"), function (n) { n.remove(); });
      var t = (c.textContent || "").replace(/\s+/g, " ").trim();
      if (t) return t;
    }
    var prev = sel.previousElementSibling;
    while (prev && prev.classList && prev.classList.contains("teampick-trigger")) prev = prev.previousElementSibling;
    if (prev && /label/i.test(prev.className || "")) {
      var p = (prev.textContent || "").trim();
      if (p) return p;
    }
    return sel.getAttribute("data-team-picker") === "college" ? "School" : "Team";
  }

  // ---- one instance per select ---------------------------------------------
  function current(sel) {
    var i = P_INDEX.get.call(sel);
    return i >= 0 ? sel.options[i] : null;
  }

  function sync(inst) {
    var sel = inst.sel, t = inst.trigger;
    if (!t) return;
    var o = current(sel);
    var m = o ? model(sel, o) : null;
    var key = m ? (m.value + "|" + m.text + "|" + m.logo) : "";
    if (key !== inst.key) {
      inst.key = key;
      t.innerHTML = '<span class="teampick-trigger-mark" aria-hidden="true">' + (m ? markHTML(m) : "") + "</span>"
        + '<span class="teampick-trigger-label">' + esc(m ? m.text : "") + "</span>";
      var spoken = m ? (m.club && m.text.indexOf(m.name) < 0 ? m.text + " " + m.name : m.text) : "";
      t.setAttribute("aria-label", labelText(sel) + ": " + spoken);
      t.classList.toggle("is-set", !!(m && (m.club || m.school || m.logo)));
    }
    // Mirror the select's own visibility and state. The picker hides the
    // select with a class, so an inline display:none or the hidden attribute
    // is the module saying "this control is not here now".
    var gone = sel.hidden || sel.style.display === "none";
    t.hidden = gone;
    t.disabled = !!sel.disabled;
    if ((gone || sel.disabled) && openState && openState.inst === inst) close(false);
  }

  function enhance1(sel) {
    var inst = sel._teampick;
    if (inst && inst.trigger && inst.trigger.isConnected && inst.trigger.nextElementSibling === sel) {
      sync(inst);
      return inst;
    }
    if (!sel.parentNode) return null;
    if (!inst) {
      inst = { sel: sel, trigger: null, key: null, n: ++uid };
      sel._teampick = inst;
      // Code that writes the value or the index lands on the trigger too.
      try {
        Object.defineProperty(sel, "value", { configurable: true,
          get: function () { return P_VALUE.get.call(sel); },
          set: function (v) { P_VALUE.set.call(sel, v); sync(inst); } });
        Object.defineProperty(sel, "selectedIndex", { configurable: true,
          get: function () { return P_INDEX.get.call(sel); },
          set: function (v) { P_INDEX.set.call(sel, v); sync(inst); } });
      } catch (e) { /* a frozen element keeps the observer path */ }
      // A module that puts focus back on its select after a re-render puts
      // it on the trigger, since a hidden select cannot take focus.
      sel.focus = function (opts) {
        if (inst.trigger && inst.trigger.isConnected && !inst.trigger.hidden) inst.trigger.focus(opts);
        else HTMLElement.prototype.focus.call(sel, opts);
      };
      sel.addEventListener("change", function () { sync(inst); });
    }
    var t = document.createElement("button");
    t.type = "button";
    t.className = "teampick-trigger";
    if (sel.id) t.id = sel.id + "-pick";
    // What survives a re-render: the id, else the name, else the label.
    t.setAttribute("data-teampick-key", sel.id || sel.getAttribute("name") || ("label:" + labelText(sel)));
    t.setAttribute("aria-haspopup", "listbox");
    t.setAttribute("aria-expanded", "false");
    t.addEventListener("click", function () {
      if (openState && openState.inst === inst) close(true); else openPanel(inst);
    });
    t.addEventListener("keydown", function (e) {
      if (e.key === "ArrowDown" || e.key === "ArrowUp") { e.preventDefault(); openPanel(inst, e.key === "ArrowUp" ? "last" : "active"); }
    });
    var ae = document.activeElement;
    var key = t.getAttribute("data-teampick-key");
    var hadFocus = ae === sel || (key === lastFocus.id && (!ae || ae === document.body)
      && Date.now() - lastFocus.at < FOCUS_FOLLOW_MS);
    // The trigger stands in the bar at the height the select had there
    // (census review 2026-09-25: 24px beside 27px fields on /mlbstats/, 24 beside
    // 25.6 on /ledger/ and /management/, 24 beside 44 on the PROSPX phone bars).
    // Read before the select is hidden; a select painted into a hidden panel
    // measures 0 and the trigger keeps its own height. A CSS variable rather
    // than an inline min-height, so the coarse-pointer 44px rule still wins.
    var nativeH = sel.getBoundingClientRect().height;
    if (nativeH > 0) t.style.setProperty("--teampick-h", nativeH.toFixed(1) + "px");
    sel.parentNode.insertBefore(t, sel);
    inst.trigger = t;
    inst.key = null;
    sel.classList.add("teampick-native");
    sel.setAttribute("tabindex", "-1");
    sync(inst);
    if (hadFocus && !t.hidden) t.focus({ preventScroll: true });
    return inst;
  }

  function enhance(root) {
    root = root || document;
    if (root.nodeType === 1 && root.matches && root.matches(SEL)) { enhance1(root); return; }
    if (!root.querySelectorAll) return;
    Array.prototype.forEach.call(root.querySelectorAll(SEL), enhance1);
  }

  // ---- the panel ------------------------------------------------------------
  function visibleRows() {
    if (!openState) return [];
    return Array.prototype.filter.call(openState.list.children, function (r) {
      return r.getAttribute("role") === "option" && !r.hidden && r.getAttribute("aria-disabled") !== "true";
    });
  }

  function filterRows(q) {
    var ql = (q || "").trim().toLowerCase();
    var any = false;
    Array.prototype.forEach.call(openState.list.children, function (r) {
      if (r.getAttribute("role") !== "option") return;
      var hit = !ql || (r.getAttribute("data-hay") || "").indexOf(ql) >= 0;
      r.hidden = !hit;
      if (hit) any = true;
    });
    openState.empty.hidden = any;
  }

  function position() {
    if (!openState) return;
    var t = openState.inst.trigger, panel = openState.panel;
    if (!t.isConnected || !openState.inst.sel.isConnected) { close(false); return; }
    var r = t.getBoundingClientRect();
    if (!r.width && !r.height) { close(false); return; }
    var vw = document.documentElement.clientWidth || window.innerWidth;
    var vh = window.innerHeight;
    var gutter = 16;
    var maxW = Math.min(340, vw - 2 * gutter);
    panel.style.maxWidth = maxW + "px";
    panel.style.minWidth = Math.min(Math.max(r.width, 240), maxW) + "px";
    openState.list.style.maxHeight = "";
    var pw = panel.offsetWidth, ph = panel.offsetHeight;
    var left = r.left;
    if (left + pw > vw - gutter) left = r.right - pw;   // flip to the trigger's right edge
    left = Math.max(gutter, Math.min(left, vw - gutter - pw));
    var below = vh - r.bottom - 12, above = r.top - 12;
    var top;
    if (ph <= below || below >= above) {
      top = r.bottom + 4;
      if (ph > below) openState.list.style.maxHeight = Math.max(120, openState.list.offsetHeight - (ph - below)) + "px";
    } else {
      if (ph > above) openState.list.style.maxHeight = Math.max(120, openState.list.offsetHeight - (ph - above)) + "px";
      top = r.top - 4 - panel.offsetHeight;
    }
    panel.style.left = Math.round(left) + "px";
    panel.style.top = Math.round(Math.max(4, top)) + "px";
  }

  function openPanel(inst, focusWhere) {
    if (openState) close(false);
    var sel = inst.sel, t = inst.trigger;
    if (!t || t.hidden || t.disabled) return;
    sync(inst);
    var college = sel.getAttribute("data-team-picker") === "college";
    var n = inst.n;
    var panel = document.createElement("div");
    panel.className = "teampick-panel";
    var cur = P_INDEX.get.call(sel);
    var rows = Array.prototype.map.call(sel.options, function (o, i) {
      var m = model(sel, o);
      var body = markHTML(m);
      if (m.club) {
        body += '<span class="teampick-opt-code">' + esc(m.code) + "</span>"
          + '<span class="teampick-opt-text">' + esc(m.name) + "</span>"
          + (m.extra ? '<span class="teampick-opt-extra">' + esc(m.extra) + "</span>" : "");
      } else {
        body += '<span class="teampick-opt-text">' + esc(m.text) + "</span>";
      }
      return '<div class="teampick-option' + (i === cur ? " is-active" : "") + '" role="option" tabindex="-1"'
        + ' id="teampick-' + n + "-" + i + '" data-i="' + i + '" data-hay="' + esc(m.hay) + '"'
        + ' aria-selected="' + (i === cur ? "true" : "false") + '"'
        + (m.disabled ? ' aria-disabled="true"' : "") + ">" + body + "</div>";
    }).join("");
    var listId = "teampick-list-" + n;
    var ph = college ? "Search schools" : "Search teams";
    panel.innerHTML = '<input type="search" class="teampick-search" placeholder="' + ph + '" aria-label="' + ph + '"'
      + ' aria-controls="' + listId + '" autocomplete="off" spellcheck="false">'
      + '<div class="teampick-options" role="listbox" id="' + listId + '" aria-label="' + esc(labelText(sel)) + '">'
      + rows + '<div class="teampick-empty" hidden>No match</div></div>';
    document.body.appendChild(panel);
    var search = panel.querySelector(".teampick-search");
    var list = panel.querySelector(".teampick-options");
    openState = { inst: inst, panel: panel, search: search, list: list, empty: list.querySelector(".teampick-empty") };
    t.setAttribute("aria-expanded", "true");
    t.setAttribute("aria-controls", listId);
    position();

    search.addEventListener("input", function () { filterRows(search.value); position(); });
    search.addEventListener("keydown", onSearchKey);
    list.addEventListener("keydown", onRowKey);
    list.addEventListener("click", function (e) {
      var row = e.target.closest ? e.target.closest(".teampick-option") : null;
      if (row && row.getAttribute("aria-disabled") !== "true") choose(+row.getAttribute("data-i"));
    });
    panel.addEventListener("focusout", function (e) {
      var to = e.relatedTarget;
      if (!openState || openState.panel !== panel) return;
      if (to && (panel.contains(to) || to === t)) return;
      if (to) close(false);   // focus went somewhere else on the page
    });

    var active = list.querySelector(".teampick-option.is-active");
    if (active) active.scrollIntoView({ block: "nearest" });
    var coarse = window.matchMedia && window.matchMedia("(pointer: coarse)").matches;
    if (focusWhere === "last") { var v = visibleRows(); if (v.length) v[v.length - 1].focus(); }
    else if (focusWhere === "active" || coarse) { (active || visibleRows()[0] || search).focus({ preventScroll: true }); }
    else search.focus({ preventScroll: true });
  }

  function close(refocus) {
    if (!openState) return;
    var st = openState;
    openState = null;
    if (st.panel.parentNode) st.panel.parentNode.removeChild(st.panel);
    var t = st.inst.trigger;
    if (t) {
      t.setAttribute("aria-expanded", "false");
      t.removeAttribute("aria-controls");
      if (refocus && t.isConnected && !t.hidden) t.focus({ preventScroll: true });
    }
  }

  function moveTo(rows, i) {
    if (!rows.length) return;
    i = Math.max(0, Math.min(rows.length - 1, i));
    rows[i].focus();
    rows[i].scrollIntoView({ block: "nearest" });
  }

  function onSearchKey(e) {
    var rows = visibleRows();
    if (e.key === "ArrowDown") { e.preventDefault(); moveTo(rows, 0); }
    else if (e.key === "ArrowUp") { e.preventDefault(); moveTo(rows, rows.length - 1); }
    else if (e.key === "Enter") {
      e.preventDefault();
      // An empty query means "keep what is chosen": the first row is "All",
      // and taking it would silently reset the filter.
      if (!openState.search.value.trim()) close(true);
      else if (rows.length) choose(+rows[0].getAttribute("data-i"));
    }
    else if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); close(true); }
    // Tab closes and returns to the trigger WITHOUT preventDefault, so the
    // browser's own Tab then moves on to the next control.
    else if (e.key === "Tab") { close(true); }
  }

  function onRowKey(e) {
    var row = e.target.closest ? e.target.closest(".teampick-option") : null;
    if (!row) return;
    var rows = visibleRows(), i = rows.indexOf(row);
    var k = e.key;
    if (k === "ArrowDown") { e.preventDefault(); moveTo(rows, i + 1); }
    else if (k === "ArrowUp") {
      e.preventDefault();
      if (i <= 0) openState.search.focus(); else moveTo(rows, i - 1);
    }
    else if (k === "Home") { e.preventDefault(); moveTo(rows, 0); }
    else if (k === "End") { e.preventDefault(); moveTo(rows, rows.length - 1); }
    else if (k === "Enter" || k === " ") { e.preventDefault(); choose(+row.getAttribute("data-i")); }
    else if (k === "Escape") { e.preventDefault(); e.stopPropagation(); close(true); }
    else if (k === "Tab") { close(true); }
    else if (k === "Backspace") {
      e.preventDefault();
      var s = openState.search;
      s.value = s.value.slice(0, -1); s.focus(); filterRows(s.value); position();
    } else if (k.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) {
      // type-ahead: the keystroke goes to the search box, and stops here so
      // the site's "/" quick-search shortcut never sees it
      e.preventDefault();
      e.stopPropagation();
      var s2 = openState.search;
      s2.value += k; s2.focus(); filterRows(s2.value); position();
    }
  }

  function choose(i) {
    if (!openState) return;
    var inst = openState.inst, sel = inst.sel;
    var changed = P_INDEX.get.call(sel) !== i;
    close(false);
    if (changed) {
      P_INDEX.set.call(sel, i);
      sync(inst);
      sel.dispatchEvent(new Event("input", { bubbles: true }));
      sel.dispatchEvent(new Event("change", { bubbles: true }));
    }
    // The module usually re-renders on change, which replaces the select and
    // this trigger; land focus on the picker that took its place.
    if (inst.trigger && inst.trigger.isConnected && !inst.trigger.hidden) {
      if (document.activeElement !== inst.trigger && (document.activeElement === document.body || !document.activeElement || !changed)) {
        inst.trigger.focus({ preventScroll: true });
      }
      return;
    }
    if (sel.id) {
      var next = document.getElementById(sel.id);
      if (next && next.matches && next.matches(SEL)) {
        var ni = enhance1(next);
        if (ni && ni.trigger && !ni.trigger.hidden && (document.activeElement === document.body || document.activeElement === next)) {
          ni.trigger.focus({ preventScroll: true });
        }
      }
    }
  }

  // ---- global wiring ----------------------------------------------------------
  document.addEventListener("focusin", function (e) {
    var tg = e.target;
    if (tg && tg.classList && tg.classList.contains("teampick-trigger")) lastFocus = { id: tg.getAttribute("data-teampick-key") || "", at: Date.now() };
    else if (tg && tg !== document.body && !(openState && openState.panel.contains(tg))) lastFocus = { id: "", at: 0 };
  }, true);
  document.addEventListener("pointerdown", function (e) {
    if (!openState) return;
    var tg = e.target;
    if (openState.panel.contains(tg) || openState.inst.trigger.contains(tg)) return;
    close(false);
  }, true);
  // A <label for="x"> outside the control points at the hidden select; send
  // its click to the trigger instead.
  document.addEventListener("click", function (e) {
    var lab = e.target && e.target.closest ? e.target.closest("label") : null;
    if (!lab || !lab.control || !lab.control._teampick) return;
    var t = lab.control._teampick.trigger;
    if (t && t.isConnected && !t.contains(e.target)) { e.preventDefault(); t.focus(); }
  }, true);
  window.addEventListener("resize", function () { if (openState) position(); });
  window.addEventListener("scroll", function (e) {
    if (!openState) return;
    if (openState.panel.contains(e.target)) return;   // the list's own scroll
    position();
  }, true);

  function observe() {
    var mo = new MutationObserver(function (muts) {
      for (var k = 0; k < muts.length; k++) {
        var m = muts[k], tg = m.target;
        if (m.type === "attributes") {
          if (tg._teampick) sync(tg._teampick);
          continue;
        }
        // an option list rewritten under a live picker
        if (tg.tagName === "SELECT" || tg.tagName === "OPTGROUP") {
          var s = tg.tagName === "SELECT" ? tg : tg.parentNode;
          if (s && s._teampick) sync(s._teampick);
          continue;
        }
        var added = m.addedNodes;
        for (var j = 0; j < added.length; j++) {
          var n = added[j];
          if (n.nodeType !== 1) continue;
          if (n.tagName === "SELECT") { if (n.hasAttribute("data-team-picker")) enhance1(n); continue; }
          if (n.firstElementChild && n.classList && !n.classList.contains("teampick-panel")
              && !n.classList.contains("teampick-trigger")) {
            var found = n.querySelectorAll(SEL);
            for (var q = 0; q < found.length; q++) enhance1(found[q]);
          }
        }
        if (m.removedNodes.length && openState && !openState.inst.sel.isConnected) close(false);
      }
    });
    mo.observe(document.body, { childList: true, subtree: true, attributes: true,
                                attributeFilter: ["style", "hidden", "disabled"] });
  }

  function start() {
    enhance(document);
    observe();
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();

  window.EephusTeamPick = { enhance: enhance, close: function () { close(false); },
                            sync: function (sel) { if (sel && sel._teampick) sync(sel._teampick); } };
})();
