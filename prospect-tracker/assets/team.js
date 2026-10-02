/* Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
 * Unauthorized copying of this file, via any medium is strictly prohibited
 * Proprietary and confidential
 * Written by Noah J. Dengler (@ARKNDJL), 2026 */

// /team/ - the Masthead cards (owner decisions TEAM-3 to TEAM-7, 2026-10-02).
//
// The page is server-rendered by build_site.build_team from the roster file;
// this file only turns cards and exports one. Three jobs:
//   1. The turn. Every card has a Back / Front button (keyboard and screen
//      reader reachable) and a click anywhere on a card front that is not a
//      link or a button turns it too. The turn itself is CSS: whole-pixel
//      steps, the base style the settled face (assets/team.css). Focus follows
//      the turn to the other face's button once the new face is showing.
//   2. "Show card backs": one toolbar toggle turns the whole set; the choice is
//      remembered per viewer (localStorage, wrapped: a private window or
//      blocked storage leaves the fronts showing, which is the default).
//   3. Share: hands one card to the shared GFX engine (assets/eephus-gfx.js,
//      kind "draw"), which paints it at 2x and exports a PNG. The button stays
//      hidden when the engine is absent.
(function () {
  "use strict";

  var STORE_KEY = "eephus.masthead.backs";
  var TURN_MS = 260;   // the .24s turn in team.css, plus one frame

  function cards() {
    return Array.prototype.slice.call(document.querySelectorAll(".tc-card:not(.is-unnamed)"));
  }

  function turn(card, toBack, moveFocus) {
    if (!card || card.classList.contains("is-unnamed")) return;
    if (card.classList.contains("is-flipped") === !!toBack) return;
    // Alternate the two identical keyframe names so a second turn restarts
    // the animation instead of inheriting the finished one.
    var nextA = !card.classList.contains("tc-turn-a");
    card.classList.remove("tc-turn-a", "tc-turn-b");
    card.classList.add(nextA ? "tc-turn-a" : "tc-turn-b");
    card.classList.toggle("is-flipped", !!toBack);
    if (moveFocus) {
      var sel = toBack ? '.tc-back .tc-flipbtn' : '.tc-front .tc-flipbtn';
      setTimeout(function () {
        var b = card.querySelector(sel);
        if (b) { try { b.focus({ preventScroll: true }); } catch (e) { b.focus(); } }
      }, TURN_MS);
    }
  }

  function readPref() {
    try { return window.localStorage.getItem(STORE_KEY) === "1"; } catch (e) { return false; }
  }
  function writePref(on) {
    try { window.localStorage.setItem(STORE_KEY, on ? "1" : "0"); } catch (e) { /* storage blocked */ }
  }

  function setAll(on, animate) {
    var btn = document.querySelector(".tc-flipall");
    if (btn) btn.setAttribute("aria-pressed", on ? "true" : "false");
    cards().forEach(function (c) {
      if (animate) turn(c, on, false);
      else c.classList.toggle("is-flipped", on);
    });
  }

  // ---- the GFX export: one card, painted at the engine's scale (2x) --------
  function iconKey(el) {
    var u = el && el.querySelector("use");
    var h = u ? (u.getAttribute("href") || "") : "";
    var i = h.indexOf("#i-");
    return i >= 0 ? h.slice(i + 3) : "";
  }
  function text(card, sel) {
    var el = card.querySelector(sel);
    return el ? el.textContent.replace(/\s+/g, " ").trim() : "";
  }
  function fit(g, t, max) {
    t = String(t || "");
    if (g.measureText(t).width <= max) return t;
    while (t.length > 1 && g.measureText(t + "...").width > max) t = t.slice(0, -1);
    return t + "...";
  }
  function loadImage(src) {
    return new Promise(function (resolve) {
      if (!src) { resolve(null); return; }
      var im = new Image();
      im.onload = function () { resolve(im); };
      im.onerror = function () { resolve(null); };
      im.src = src;
    });
  }

  async function paint(card, env) {
    var S = env.scale || 2, P = env.palette, X = env.px;
    var W = 300, H = 420;
    var owner = card.classList.contains("is-owner");
    var edge = owner ? 4 : 2;
    var c = document.createElement("canvas");
    c.width = W * S; c.height = H * S;
    var g = c.getContext("2d");
    g.scale(S, S);
    var F = P.MONO;

    // The edge: ink for every card; the owner's card the banded foil (the
    // brand ramp in hard bands, the same steps the page draws).
    if (owner) {
      var grad = g.createLinearGradient(0, 0, W, H);
      var n = P.ramp.length;
      P.ramp.forEach(function (s, k) {
        grad.addColorStop(k / n, s[1]);
        grad.addColorStop(Math.min(1, (k + 1) / n - 0.0001), s[1]);
      });
      g.fillStyle = grad;
    } else {
      g.fillStyle = P.fg;
    }
    g.fillRect(0, 0, W, H);
    g.fillStyle = P.bg2;
    g.fillRect(edge, edge, W - 2 * edge, H - 2 * edge);

    var x0 = edge + 10, x1 = W - edge - 10, cw = x1 - x0;
    g.textBaseline = "alphabetic";

    // top line: card number and set name
    g.fillStyle = P.fg; g.font = "700 12px " + F;
    var no = text(card, ".tc-front .tc-no");
    g.fillText(no, x0, edge + 22);
    g.fillStyle = P.sub; g.font = "12px " + F;
    var set = text(card, ".tc-front .tc-set").toUpperCase();
    var setT = fit(g, set, cw - g.measureText(no).width - 12);
    g.fillText(setT, x1 - g.measureText(setT).width, edge + 22);

    // the photo window
    var py = edge + 30, ph = 206;
    g.fillStyle = P.fg; g.fillRect(x0, py, cw, ph);
    g.fillStyle = P.bg2; g.fillRect(x0 + 2, py + 2, cw - 4, ph - 4);
    var imgEl = card.querySelector(".tc-photo img");
    var im = await loadImage(imgEl ? (imgEl.currentSrc || imgEl.src) : "");
    if (im) {
      var bw = cw - 4, bh = ph - 4;
      var sc = Math.max(bw / im.naturalWidth, bh / im.naturalHeight);
      var sw = bw / sc, sh = bh / sc;
      var sx = (im.naturalWidth - sw) / 2, sy = (im.naturalHeight - sh) * 0.22;
      g.drawImage(im, sx, sy, sw, sh, x0 + 2, py + 2, bw, bh);
    } else {
      var ini = text(card, ".tc-mono");
      g.fillStyle = P.sub; g.font = "700 48px " + F;
      g.fillText(ini, x0 + cw / 2 - g.measureText(ini).width / 2, py + ph / 2 + 16);
    }
    // the photo window's notched corners: one cut pixel at each
    g.fillStyle = P.bg2;
    [[x0, py], [x1 - 2, py], [x0, py + ph - 2], [x1 - 2, py + ph - 2]].forEach(function (p) {
      g.fillRect(p[0], p[1], 2, 2);
    });
    if (owner) {
      var plate = "OWNER AND FOUNDER";
      g.font = "700 12px " + F;
      var pw = 6 + 12 + 4 + g.measureText(plate).width + 6;
      var pyy = py + ph - 6 - 20;
      g.fillStyle = P.fg; g.fillRect(x0 + 6, pyy, pw, 20);
      g.fillStyle = P.bg; g.fillRect(x0 + 8, pyy + 2, pw - 4, 16);
      if (X && X.hasIcon("b-founder")) X.pxIcon(g, "b-founder", x0 + 12, pyy + 4, 1, P.fg, P.accent);
      g.fillStyle = P.fg;
      g.fillText(plate, x0 + 12 + 12 + 4, pyy + 15);
    }

    // the name plate
    var ny = py + ph + 8;
    g.fillStyle = P.fg; g.fillRect(x0, ny, cw, 30);
    g.fillStyle = P.bg; g.font = "700 24px " + F;
    g.fillText(fit(g, text(card, ".tc-name"), cw - 12), x0 + 6, ny + 23);

    // position and team lines
    var ly = ny + 30 + 16;
    g.fillStyle = P.fg; g.font = "700 12px " + F;
    g.fillText(fit(g, text(card, ".tc-pos").toUpperCase(), cw), x0, ly);
    ly += 18;
    var teamEl = card.querySelector(".tc-team");
    var tx = x0;
    if (X && teamEl && X.hasIcon(iconKey(teamEl))) { X.pxIcon(g, iconKey(teamEl), x0, ly - 11, 1, P.sub); tx += 16; }
    g.fillStyle = P.sub; g.font = "12px " + F;
    g.fillText(fit(g, text(card, ".tc-team").toUpperCase(), x1 - tx), tx, ly);

    // the stats line: one 12 px badge per credit, wrapped
    var bx = x0, by = ly + 10;
    var badges = card.querySelectorAll(".tc-front .tc-badge");
    for (var i = 0; i < badges.length; i++) {
      var k = iconKey(badges[i]);
      if (!X || !X.hasIcon(k)) continue;
      if (bx + 12 > x1) { bx = x0; by += 18; }
      X.pxIcon(g, k, bx, by, 1, P.fg, P.accent);
      bx += 18;
    }
    var more = text(card, ".tc-more");
    if (more) {
      g.fillStyle = P.fg; g.font = "700 12px " + F;
      if (bx + g.measureText(more).width > x1) { bx = x0; by += 18; }
      g.fillText(more, bx, by + 11);
    }

    // foot: the address and the set line
    g.fillStyle = P.fg; g.font = "700 12px " + F;
    var url = "eephus.io/team/";
    g.fillText(url, x0, H - edge - 10);
    g.fillStyle = P.sub; g.font = "12px " + F;
    var tail = fit(g, no, cw - g.measureText(url).width - 12);
    g.fillText(tail, x1 - g.measureText(tail).width, H - edge - 10);
    return c;
  }

  function share(card) {
    var G = window.EEPHUS_GFX;
    if (!G || !card) return;
    var name = text(card, ".tc-name");
    G.open({
      kind: "draw",
      module: "Masthead",
      accentToken: "--accent-lilac",
      title: name + " - eephus.io Masthead",
      url: "eephus.io/team/",
      filenameBase: "eephus-masthead-" + (card.getAttribute("data-member") || "card"),
      draw: function (env) { return paint(card, env); },
    });
  }

  function init() {
    var root = document.querySelector(".tc-set-wrap");
    if (!root) return;

    if (window.EEPHUS_GFX && window.EEPHUS_HUB) {
      root.querySelectorAll("[data-gfx]").forEach(function (b) { b.hidden = false; });
    }

    root.addEventListener("click", function (e) {
      var card = e.target.closest(".tc-card");
      if (!card) return;
      var flip = e.target.closest("[data-flip]");
      if (flip) {
        e.preventDefault();
        turn(card, flip.getAttribute("data-flip") === "back", true);
        return;
      }
      var gfx = e.target.closest("[data-gfx]");
      if (gfx) { e.preventDefault(); share(card); return; }
      if (e.target.closest("a, button, input, select, textarea")) return;
      if (e.target.closest(".tc-front")) turn(card, true, false);
    });

    var all = document.querySelector(".tc-flipall");
    if (all) {
      all.addEventListener("click", function () {
        var on = all.getAttribute("aria-pressed") !== "true";
        setAll(on, true);
        writePref(on);
      });
    }
    if (readPref()) setAll(true, false);

    // A deep link to a card (/team/#member-<key>) always opens on its front.
    if (location.hash && location.hash.indexOf("#member-") === 0) {
      var target = document.getElementById(location.hash.slice(1));
      if (target) target.classList.remove("is-flipped");
    }
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();

  window.EephusMasthead = { turn: turn, paint: paint };
})();
