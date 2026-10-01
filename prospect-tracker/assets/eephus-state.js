/* =============================================================================
   eephus.io - the pixel state component (final-pass plan 5.7, PX-11)
   -----------------------------------------------------------------------------
   One box for the four states a board can be in when it has no rows to show,
   drawn in the ballpark lamp idiom (owner answer PX-Q1, 2026-09-24):

     loading     the wordmark's lob arc on a 46 x 18 lamp grid at 2x; an ink
                 ball steps along the dotted track and settles. The only loop.
     empty       filtered to zero: the on-deck circle with a bat beside it.
     unmeasured  not measured or not built yet: an unlit "- -" scoreboard.
     failed      the fetch failed: the scoreboard reads E. role=alert.

   The caller keeps its own message and passes it in as HTML it has already
   escaped (a Retry button rides inside it, so its id and handler stay the
   caller's). The art is aria-hidden; the message carries the meaning.

   WHY A HEAD SCRIPT AND NOT eephus-ui.js: the account layer rides the block
   injected after the page body, and every module paints its loading line
   synchronously when its own deferred script runs, which is before that block.
   This file loads in the head next to the value ruler, so the component is
   defined before any board renders (deferred scripts run in document order).

   Motion: CSS only (assets/site.css, the .px-state block), step-end, no timer
   and no animation-frame loop here. Under prefers-reduced-motion the loader
   holds the ball at the apex of the arc.
   ========================================================================== */
(function () {
  "use strict";
  // The lob: one 2 x 2 ball per frame, 0.1 s apart on a 1.6 s loop. Frame 6 is
  // the apex and the still frame (class r). The last three frames are the
  // drop, settle and hold the logo's own ball makes.
  var LOB = [[0, 15], [4, 11], [7, 7], [11, 5], [15, 3], [18, 1], [22, 1], [26, 1], [29, 3],
             [33, 5], [37, 7], [40, 11], [44, 15], [44, 16], [44, 15], [44, 15]];
  var REST = 6;
  function lob() {
    var r = "";
    for (var i = 0; i < LOB.length; i++) {
      r += '<rect class="f' + (i === REST ? " r" : "") + '" x="' + LOB[i][0] + '" y="' + LOB[i][1] +
        '" width="2" height="2" style="animation-delay:' + (i * 0.1 - 1.6).toFixed(1) + 's"/>';
    }
    return '<span class="px-lob" aria-hidden="true"><i></i><svg width="92" height="36" viewBox="0 0 46 18" ' +
      'shape-rendering="crispEdges">' + r + "</svg></span>";
  }
  // The three still scenes, 32 x 16 lamp grids drawn at 2x. Kept byte-equal
  // to build_site.py _PX_STATE_ART (test_state_component.py pins the pair).
  var ART = {
    empty: '<svg class="px-art" aria-hidden="true" width="64" height="32" viewBox="0 0 32 16" shape-rendering="crispEdges"><path class="s" d="M10 3h12v1h-12zM6 4h4v1h-4zM22 4h4v1h-4zM4 5h2v1h-2zM26 5h2v1h-2zM3 6h1v2h-1zM28 6h1v2h-1zM4 8h2v1h-2zM26 8h2v1h-2zM6 9h4v1h-4zM22 9h4v1h-4zM10 10h12v1h-12zM4 13h2v1h-2zM4 14h16v1h-16zM4 15h2v1h-2z"/><path class="k" d="M20 13h9v1h-9zM20 14h10v1h-10zM20 15h9v1h-9z"/></svg>',
    unmeasured: '<svg class="px-art" aria-hidden="true" width="64" height="32" viewBox="0 0 32 16" shape-rendering="crispEdges"><path class="s" d="M2 1h28v1h-28zM2 2h1v9h-1zM29 2h1v9h-1zM2 11h28v1h-28zM8 12h2v3h-2zM22 12h2v3h-2zM0 15h32v1h-32z"/><path class="k" d="M10 6h5v1h-5zM16 6h5v1h-5z"/></svg>',
    failed: '<svg class="px-art" aria-hidden="true" width="64" height="32" viewBox="0 0 32 16" shape-rendering="crispEdges"><path class="s" d="M2 1h28v1h-28zM2 2h1v9h-1zM29 2h1v9h-1zM2 11h28v1h-28zM8 12h2v3h-2zM22 12h2v3h-2zM0 15h32v1h-32z"/><path class="k" d="M13 3h5v1h-5zM13 4h1v2h-1zM13 6h4v1h-4zM13 7h1v2h-1zM13 9h5v1h-5z"/></svg>'
  };
  var KINDS = ["loading", "empty", "unmeasured", "failed"];
  // opts: a string is one extra class (a hook a test or a module selector
  // reads); an object may carry { cls, role }.
  function html(kind, msg, opts) {
    var k = KINDS.indexOf(kind) >= 0 ? kind : "empty";
    var o = typeof opts === "string" ? { cls: opts } : (opts || {});
    var role = o.role || (k === "failed" ? "alert" : (k === "loading" ? "status" : ""));
    return '<div class="px-state is-' + k + (o.cls ? " " + o.cls : "") + '"' +
      (role ? ' role="' + role + '"' : "") + (k === "loading" ? ' aria-live="polite"' : "") + ">" +
      (k === "loading" ? lob() : ART[k]) +
      '<div class="px-state-msg">' + (msg == null ? "" : msg) + "</div></div>";
  }
  function render(el, kind, msg, opts) {
    if (el) el.innerHTML = html(kind, msg, opts);
    return el;
  }
  window.EephusState = { html: html, render: render, kinds: KINDS.slice() };
})();
