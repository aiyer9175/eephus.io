// Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
// Unauthorized copying of this file, via any medium is strictly prohibited
// Proprietary and confidential
// Written by Noah J. Dengler (@ARKNDJL), 2026
//
// The /fantasy/ coordinator. It renders no board and owns no column.
//
// WHAT IT IS FOR. /fantasy/ carries three sub-modules (Redraft, Dynasty, DFS)
// that were three separate pages between 2026-08-05 and 2026-08-07. Merging
// them back into one document put three independent clients in one window, and
// three things that were safe on three pages stop being safe in one:
//
//   1. MOUNT IDS. Every client resolves its root through a candidate list that
//      ends at the fantasy-era "#fantasy-app-root". A combined shell exposing
//      that id would hand the SAME node to all three, and the last one to
//      paint would win. The shell therefore emits each client's own ids and
//      never the shared fallback, and test_fantasy_split pins that absence.
//   2. THE HASH. Each client owns "#section=" over its own vocabulary and
//      rewrites the address bar from its own state. Three of them on one page
//      is three writers racing over one string. So the address bar is owned
//      HERE: the hash is "#m=<module>&<that module's own hash>", each client
//      reads and writes only its half through this file, and only the ACTIVE
//      module's half is in the URL.
//   3. THE PAYLOAD. data/fantasy.json is 576KB and both Redraft and Dynasty
//      read it. One memoized load serves both, and the DFS card as well.
//
// LAZY BOOT. A client's script tag is injected on the first activation of its
// module, so a reader who opens Redraft and leaves never downloads the DFS
// client or the DFS slate, and a reader who never leaves Redraft never
// downloads the other two clients at all.
//
// NOTHING HERE IS A MODEL. No number in this file, no grade, no scoring, no
// sort. It moves panels and it owns one string.
(function () {
  "use strict";

  // The shared corpus. The URL lives here and not in a client, because a
  // client that names a sidecar it does not own is a client that has started
  // building a second corpus (test_fantasy_split pins one /data/ literal per
  // client for exactly that reason).
  var CORPUS_URL = "/data/fantasy.json";

  var MODS = [];        // module ids, in module-bar order; MODS[0] is the default
  var BTN = {};         // id -> the module-bar button
  var PANEL = {};       // id -> the module's panel
  var SUB = {};         // id -> that module's own hash, WITHOUT the leading "#"
  var ONCHANGE = {};    // id -> the client's own route handler
  var BOOTED = {};
  var ACTIVE = null;
  var LOADS = {};       // url -> in-flight or settled JSON promise

  // ---- the legacy hash table ------------------------------------------------
  // Every section name that has ever addressed one of these boards, and the
  // module that owns it now. This is what lets a hash with no "m=" resolve at
  // all: the three vocabularies are DISJOINT, so a bare "#section=ros_sp" names
  // exactly one module.
  //
  // It covers four generations of link: the pre-split /fantasy/ page (its nine
  // sections, which are Redraft's seven plus callups and dynasty), the three
  // split pages, the pre-split aliases those pages already accept (board,
  // pitchers, hitters, salaries), and the "keeper" tab that only ever existed
  // after the split. A name that resolves nowhere lands on the default module
  // rather than on a blank page.
  var SECTION_HOME = {
    streamers: "redraft", two_start: "redraft", ros_sp: "redraft",
    ros_rp: "redraft", ros_hitter: "redraft", buysell: "redraft",
    closers: "redraft",
    dynasty: "dynasty", board: "dynasty", callups: "dynasty", keeper: "dynasty",
    slate: "dfs", value: "dfs", stacks: "dfs", optimizer: "dfs",
    pitchers: "dfs", hitters: "dfs", salaries: "dfs"
  };
  // hasOwnProperty, not a bare lookup: "#section=constructor" is inherited off
  // Object.prototype, truthy, and would resolve to a module. The frozen
  // pre-split client hit this exact trap and left the same note.
  function homeOf(name) {
    return (name && Object.prototype.hasOwnProperty.call(SECTION_HOME, name))
      ? SECTION_HOME[name] : null;
  }

  // ---- hash plumbing --------------------------------------------------------
  function raw() { return location.hash || ""; }
  function modOf(h) {
    var m = /(?:^#|[#&])m=([a-z]+)(?:&|$)/.exec(h || "");
    return (m && MODS.indexOf(m[1]) >= 0) ? m[1] : null;
  }
  // The module's own half: everything except the m= key, order preserved.
  function subOf(h) {
    var parts = String(h || "").replace(/^#/, "").split("&");
    var keep = [];
    for (var i = 0; i < parts.length; i++) {
      if (parts[i] && !/^m=/.test(parts[i])) keep.push(parts[i]);
    }
    return keep.join("&");
  }
  function sectionOf(h) {
    var m = /(?:^#|[#&])section=([a-z_]+)(?:&|$)/.exec(h || "");
    return m ? m[1] : null;
  }
  // Which module a hash names, and what is left for it. An "m=" wins; failing
  // that a legacy "#section=" is resolved through the table; failing that the
  // default module takes it, params and all, because a hash carrying only
  // "#player=1234" is a card link off the pre-merge Redraft board.
  function route(h) {
    var mod = modOf(h);
    if (!mod) mod = homeOf(sectionOf(h)) || MODS[0];
    return { mod: mod, sub: subOf(h) };
  }
  function compose(mod, sub) {
    return "#m=" + mod + (sub ? "&" + sub : "");
  }
  function stamp() {
    var want = compose(ACTIVE, SUB[ACTIVE] || "");
    if (raw() === want) return;
    // replaceState, never pushState: a board that pushed a history entry per
    // sort click would make the Back button a sort-undo button.
    try { history.replaceState(null, "", want); } catch (e) { /* the hash is a nicety */ }
  }

  // ---- panels ---------------------------------------------------------------
  function show(mod) {
    for (var i = 0; i < MODS.length; i++) {
      var id = MODS[i], on = id === mod;
      if (PANEL[id]) {
        if (on) PANEL[id].removeAttribute("hidden");
        else PANEL[id].setAttribute("hidden", "hidden");
      }
      if (BTN[id]) {
        BTN[id].classList.toggle("active", on);
        BTN[id].setAttribute("aria-selected", on ? "true" : "false");
      }
    }
  }
  // The client's script tag, injected once. An unreachable client is a loud
  // note in its own panel, not an empty box: the reader clicked a module and
  // something has to answer.
  function bootModule(mod) {
    if (BOOTED[mod]) return;
    BOOTED[mod] = true;
    var src = BTN[mod] && BTN[mod].getAttribute("data-src");
    var panel = PANEL[mod];
    if (!src) { fail(panel, "This module has no client bundle on the page."); return; }
    var s = document.createElement("script");
    s.src = src;
    s.onerror = function () {
      fail(panel, "The module script did not load. The nightly build may be mid-run.");
    };
    document.head.appendChild(s);
  }
  function fail(panel, msg) {
    if (!panel) return;
    var root = panel.querySelector ? panel.querySelector("[id$='-app-root']") : null;
    if (root) root.innerHTML = '<div class="fh-error" role="alert"><strong>' + msg + "</strong></div>";
  }

  // ---- activation -----------------------------------------------------------
  // `sub` undefined means "keep whatever that module was last showing", which
  // is what makes the module bar feel like tabs rather than three reloads.
  function activate(mod, sub) {
    if (MODS.indexOf(mod) < 0) mod = MODS[0];
    if (sub != null) SUB[mod] = sub;
    ACTIVE = mod;
    show(mod);
    stamp();
    if (!BOOTED[mod]) { bootModule(mod); return; }
    if (ONCHANGE[mod]) ONCHANGE[mod]();
  }

  // A reader-driven hash change: the address bar, a card link, the Back button.
  // Our own writes go through stamp(), and replaceState does not fire this.
  function onHashChange() {
    var r = route(raw());
    if (r.mod !== ACTIVE) { activate(r.mod, r.sub); return; }
    SUB[ACTIVE] = r.sub;
    if (ONCHANGE[ACTIVE]) ONCHANGE[ACTIVE]();
  }

  // ---- the host API the clients bind to -------------------------------------
  // Each client keeps its own router; it just stops reaching for `location` and
  // `window` directly. With no host on the page (the JS-engine harness, or a
  // client driven standalone) every one of these falls back to the plain
  // browser call, which is why the parity harness still drives redraft.js with
  // no shell around it.
  var HOST = {
    // The module's own half of the hash, with the leading "#" a client's
    // hashParam regexes expect.
    hash: function (mod) { return "#" + (SUB[mod] || ""); },
    // The client hands over its whole hash ("#section=..."); we own the m= key.
    write: function (mod, sub) {
      SUB[mod] = String(sub || "").replace(/^#/, "");
      if (mod === ACTIVE) stamp();
    },
    // An href a reader can copy out of the page: the full namespaced form.
    link: function (mod, sub) {
      return compose(mod, String(sub || "").replace(/^#/, ""));
    },
    onChange: function (mod, fn) { ONCHANGE[mod] = fn; },
    // One fetch per URL per session, shared by every module. A rejection is
    // NOT cached: each client offers a Retry button and a memoized failure
    // would make it a button that re-reports the same error forever.
    //
    // Callers get the SAME parsed object, so the payload is read-only by
    // contract. Redraft and Dynasty both index it and neither writes to it; a
    // client that started editing the corpus in place would be editing the
    // other module's board.
    json: function (url) {
      if (!LOADS[url]) {
        LOADS[url] = fetch(url, { cache: "no-cache" }).then(function (r) {
          if (!r.ok) throw new Error("HTTP " + r.status);
          return r.json();
        }).catch(function (e) { delete LOADS[url]; throw e; });
      }
      return LOADS[url];
    },
    // The shared board corpus, for a module that needs it for the player card
    // but does not read it for its own boards (that is DFS: its slate is its
    // own sidecar, and the card is a lookup into the season corpus).
    corpus: function () { return HOST.json(CORPUS_URL); }
  };

  // ---- boot -----------------------------------------------------------------
  function init() {
    var bar = document.querySelectorAll("[data-fantasymodule]");
    if (!bar || !bar.length) return;          // not the combined page
    for (var i = 0; i < bar.length; i++) {
      var id = bar[i].getAttribute("data-fantasymodule");
      if (!id || MODS.indexOf(id) >= 0) continue;
      MODS.push(id);
      BTN[id] = bar[i];
      PANEL[id] = document.querySelector('[data-fantasypanel="' + id + '"]');
      SUB[id] = "";
      (function (mod, btn) {
        btn.addEventListener("click", function () { activate(mod, undefined); });
      }(id, bar[i]));
    }
    if (!MODS.length) return;
    window.addEventListener("hashchange", onHashChange);
    var r = route(raw());
    activate(r.mod, r.sub);
  }

  window.EEPHUS_FANTASY_HOST = HOST;
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();

  // ---- module-bar styles (theme tokens only) --------------------------------
  // The bar is the one piece of furniture this file owns. It reads as a level
  // ABOVE the section nav on purpose: the split's whole complaint was that the
  // dynasty board sat behind seven redraft tabs, and a switcher that looked
  // like an eighth tab would put it back there.
  var css = document.createElement("style");
  css.textContent = [
    ".fantasy-modbar{display:flex;flex-wrap:wrap;gap:0;margin:14px 0 4px;border-bottom:2px solid var(--border)}",
    ".fantasy-modbtn{font:700 13px/1 var(--font-retro,monospace);letter-spacing:.04em;",
    "text-transform:uppercase;padding:11px 18px;border:1px solid var(--border);",
    "border-bottom:none;margin-right:4px;",
    "background:var(--bg-secondary);color:var(--text-tertiary);cursor:pointer;position:relative;top:2px}",
    ".fantasy-modbtn:hover{color:var(--text-primary)}",
    ".fantasy-modbtn.active{background:var(--accent-cyan);color:var(--text-on-accent);border-color:transparent}",
    ".fantasy-modbtn .fh-modsub{display:block;font:500 10px/1.2 var(--font-retro,monospace);",
    "text-transform:none;letter-spacing:0;opacity:.8;margin-top:3px}",
    ".fantasy-mod[hidden]{display:none}",
    ".fantasy-modsub{display:block;font-size:12.5px;color:var(--text-secondary);margin:10px 0 2px}",
    ".fh-error{border:1px solid var(--accent-red);padding:12px;color:var(--text-primary);background:var(--bg-secondary)}",
    "@media (max-width:560px){.fantasy-modbtn{flex:1 1 auto;padding:10px 8px;text-align:center}",
    ".fantasy-modbtn .fh-modsub{display:none}}"
  ].join("");
  document.head.appendChild(css);
})();
