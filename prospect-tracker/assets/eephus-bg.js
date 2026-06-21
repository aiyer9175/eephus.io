// eephus.io - dark-theme starfield background (shared component).
// Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
//
// One fixed, full-viewport <canvas id="eephus-bg"> behind all content, on BOTH
// surfaces (editorial pages + the PROSPX app). The radial glow + corner vignette
// + faint scanlines are CSS background layers on the element itself
// (assets/site.css, dark scope); this module draws the stars.
//
// Y2K / chrome-holo aesthetic: crisp PIXEL sparkle-stars (no anti-aliased
// circles) - a bright center pixel with a twinkling 4-point "+" of pixels and a
// soft square bloom - in an iridescent blue/purple/cyan/magenta holo palette
// that slowly shimmers through the ramp like a hologram. A few bright white-blue
// stars anchor the field. It stays a background: low opacity, aria-hidden,
// content always sits on solid cards above it.
//
// Dark-theme gating: a MutationObserver on <html data-theme> mounts the canvas
// when the dark theme activates and FULLY tears it down on any other theme.
//
// Hard guardrails (constants, NOT dialable via tokens):
//   • exactly one requestAnimationFrame loop, paused while document.hidden
//   • absolute star-count ceiling regardless of viewport size
//   • devicePixelRatio capped at 2
//   • the twinkle ALWAYS runs (owner ask: a static starfield looks dead). The
//     field is whisper-opacity aria-hidden decoration, so it keeps twinkling
//     even under prefers-reduced-motion; only the user-tracking parallax honors
//     the OS motion preference (it reads very differently). The hidden-tab pause
//     is unconditional.
//
// FV linkage (PROSPX prospect views): the app calls EephusBG.setFV(fv) on route
// changes. Intensity t = clamp((fv - 45) / (70 - 45), 0, 1) - the audited
// card-rarity thresholds. Higher t = a denser, brighter, more saturated field.
(function () {
  "use strict";

  var MAX_STARS = 260;        // absolute ceiling, any viewport, any FV
  var MAX_DPR = 2;            // retina fill-cost bound
  var MAX_PARALLAX_PX = 6;    // total scroll/pointer drift budget at the deepest layer
  var FV_FLOOR = 45;          // rankNumRarityClass: lowest rarity tier (shine)
  var FV_CEIL = 70;           // rankNumRarityClass: top rarity tier (legendary)
  var LAYER_DEPTHS = [0.4, 0.7, 1.0];

  var canvas = null, ctx = null, rafId = null;
  var stars = [];
  var ramp = null;            // holo color ramp (parsed at mount)
  var brightCol = [221, 235, 255];
  var tokens = null;
  var fvT = 0;
  var scrollOff = 0, pointerX = 0;
  var teardownFns = [];
  var resizeTimer = null;

  var reducedMq = window.matchMedia ? window.matchMedia("(prefers-reduced-motion: reduce)") : null;
  function reducedMotion() { return !!(reducedMq && reducedMq.matches); }
  function isDark() { return document.documentElement.getAttribute("data-theme") === "dark"; }

  // ---- token plumbing ------------------------------------------------------
  function cssNum(styles, name, fallback) {
    var v = parseFloat(styles.getPropertyValue(name));
    return isFinite(v) ? v : fallback;
  }
  function cssColor(styles, name, fallback) {
    var raw = (styles.getPropertyValue(name) || "").trim();
    var m = /^#([0-9a-f]{6})$/i.exec(raw);
    if (m) { var n = parseInt(m[1], 16); return [(n >> 16) & 255, (n >> 8) & 255, n & 255]; }
    m = /^#([0-9a-f]{3})$/i.exec(raw);
    if (m) return [parseInt(m[1][0] + m[1][0], 16), parseInt(m[1][1] + m[1][1], 16), parseInt(m[1][2] + m[1][2], 16)];
    m = /^rgba?\(\s*(\d+)[,\s]+(\d+)[,\s]+(\d+)/i.exec(raw);
    if (m) return [+m[1], +m[2], +m[3]];
    return fallback;
  }
  function readTokens() {
    var s = getComputedStyle(document.documentElement);
    ramp = [
      cssColor(s, "--star-holo-1", [0, 217, 255]),    // cyan
      cssColor(s, "--star-holo-2", [91, 200, 255]),   // sky
      cssColor(s, "--star-holo-3", [139, 127, 255]),  // blurple
      cssColor(s, "--star-holo-4", [180, 124, 255]),  // violet
      cssColor(s, "--star-holo-5", [255, 79, 216]),   // magenta
    ];
    brightCol = cssColor(s, "--star-color-bright", [221, 235, 255]);
    tokens = {
      density:     cssNum(s, "--star-density-base", 0.12),
      opacityMax:  cssNum(s, "--star-opacity-max", 0.55),
      speed:       cssNum(s, "--star-twinkle-speed", 1) || 1,
      holoSpeed:   cssNum(s, "--star-holo-speed", 1) || 1,
      layers:      Math.max(2, Math.min(3, Math.round(cssNum(s, "--star-parallax-layers", 3)))),
      densityMult: cssNum(s, "--star-fv-density-mult", 1.6),
      opacityMult: cssNum(s, "--star-fv-opacity-mult", 1.25),
    };
  }

  // ---- star field ----------------------------------------------------------
  function targetCount(w, h) {
    var density = tokens.density * (1 + (tokens.densityMult - 1) * fvT);
    return Math.min(MAX_STARS, Math.round((w * h) / 1000 * density));
  }
  function buildStars(w, h) {
    var n = targetCount(w, h);
    stars.length = 0;
    for (var i = 0; i < n; i++) {
      var u = Math.random();
      var mag = u * u * u;                       // 0 faint .. 1 bright (most faint)
      var layer = i % tokens.layers;
      stars.push({
        fx: Math.random(),
        fy: Math.random(),
        mag: mag,
        bright: mag > 0.82,                      // anchors: bright white-blue, 8-point
        size: 1 + Math.round(mag * 1.5),         // core pixels (1..2-3)
        arm: 1 + Math.round(mag * 2.5),          // sparkle arm length in css px
        baseB: 0.45 + 0.55 * mag,
        huePhase: Math.random(),                 // position along the holo ramp
        twPeriod: (1700 + Math.random() * 3600) / tokens.speed,
        twPhase: Math.random(),
        twAmp: 0.30 + Math.random() * 0.5,       // sparkle pulse depth
        layer: layer,
      });
    }
  }

  // Holo color: a slow shimmer along the iridescent ramp, per-star phase so the
  // field never moves in unison. Bright anchors blend toward white-blue.
  function holoColor(star, now) {
    var t = (now / (16000 / tokens.holoSpeed) + star.huePhase) % 1;
    var f = t * ramp.length;
    var i0 = Math.floor(f) % ramp.length;
    var i1 = (i0 + 1) % ramp.length;
    var k = f - Math.floor(f);
    var a = ramp[i0], b = ramp[i1];
    var r = a[0] + (b[0] - a[0]) * k, g = a[1] + (b[1] - a[1]) * k, bl = a[2] + (b[2] - a[2]) * k;
    if (star.bright) { r = (r + brightCol[0] * 2) / 3; g = (g + brightCol[1] * 2) / 3; bl = (bl + brightCol[2] * 2) / 3; }
    return (r | 0) + "," + (g | 0) + "," + (bl | 0);
  }
  // Twinkle: smooth per-star pulse (brightness + sparkle arm length).
  function twinkle(star, now) {
    return 0.5 + 0.5 * Math.sin(6.2831853 * (now / star.twPeriod + star.twPhase));
  }

  function draw(now) {
    var w = canvas.clientWidth, h = canvas.clientHeight;
    var dpr = canvas.width / Math.max(1, w);
    var u = Math.max(1, Math.round(dpr));        // 1 css px in device px (the pixel grid)
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    var alphaMax = Math.min(0.85, tokens.opacityMax * (1 + (tokens.opacityMult - 1) * fvT));
    for (var i = 0; i < stars.length; i++) {
      var st = stars[i];
      var depth = LAYER_DEPTHS[st.layer] || 1;
      var tw = twinkle(st, now);
      var b = st.baseB * (1 - st.twAmp + st.twAmp * tw);
      var a = alphaMax * Math.max(0, Math.min(1, b));
      if (a < 0.015) continue;
      var rgb = holoColor(st, now);
      var x = (st.fx * w + pointerX * depth) % w; if (x < 0) x += w;
      var y = (st.fy * h + scrollOff * depth) % h; if (y < 0) y += h;
      // snap to the device-pixel grid for crisp pixels
      var px = Math.round(x * dpr), py = Math.round(y * dpr);
      var core = st.size * u;
      var half = (core - (core % 2)) / 2;
      // soft square bloom (pixelated glow), two stepped steps
      var g1 = (st.arm + 2) * u;
      ctx.fillStyle = "rgba(" + rgb + "," + (a * 0.08).toFixed(3) + ")";
      ctx.fillRect(px - g1, py - g1, g1 * 2, g1 * 2);
      var g2 = Math.round(g1 * 0.5);
      ctx.fillStyle = "rgba(" + rgb + "," + (a * 0.14).toFixed(3) + ")";
      ctx.fillRect(px - g2, py - g2, g2 * 2, g2 * 2);
      // sparkle arms (twinkle): length pulses with the twinkle
      var arm = Math.max(0, Math.round(st.arm * (0.25 + 0.75 * tw))) * u;
      if (arm >= u) {
        ctx.fillStyle = "rgba(" + rgb + "," + (a * 0.9).toFixed(3) + ")";
        ctx.fillRect(px - arm, py - Math.floor(u / 2), arm * 2 + u, u);
        ctx.fillRect(px - Math.floor(u / 2), py - arm, u, arm * 2 + u);
        if (st.bright) {                          // 8-point: diagonal pixels on anchors
          var d = Math.round(arm * 0.55);
          ctx.fillRect(px + d, py + d, u, u); ctx.fillRect(px - d - u, py + d, u, u);
          ctx.fillRect(px + d, py - d - u, u, u); ctx.fillRect(px - d - u, py - d - u, u, u);
        }
      }
      // core pixel(s) - the brightest part
      ctx.fillStyle = "rgba(" + rgb + "," + Math.min(1, a * 1.4).toFixed(3) + ")";
      ctx.fillRect(px - half, py - half, core, core);
    }
  }

  // ---- the one animation loop (twinkle always runs) ------------------------
  function frame(now) {
    rafId = null;
    if (!canvas) return;
    draw(now);
    if (!document.hidden) rafId = requestAnimationFrame(frame);
  }
  function startLoop() {
    if (!canvas || rafId !== null) return;
    if (!document.hidden) rafId = requestAnimationFrame(frame);
  }
  function stopLoop() { if (rafId !== null) { cancelAnimationFrame(rafId); rafId = null; } }

  // ---- mount / unmount -----------------------------------------------------
  function listen(target, ev, fn, opts) {
    target.addEventListener(ev, fn, opts);
    teardownFns.push(function () { target.removeEventListener(ev, fn, opts); });
  }
  function sizeCanvas() {
    var dpr = Math.min(MAX_DPR, window.devicePixelRatio || 1);
    canvas.width = Math.round(window.innerWidth * dpr);
    canvas.height = Math.round(window.innerHeight * dpr);
  }
  function rebuild() {
    if (!canvas) return;
    sizeCanvas();
    buildStars(canvas.clientWidth || window.innerWidth, canvas.clientHeight || window.innerHeight);
    if (document.hidden) draw(performance.now());
  }
  function mount() {
    if (canvas || !document.body) return;
    readTokens();
    canvas = document.createElement("canvas");
    canvas.id = "eephus-bg";
    canvas.setAttribute("aria-hidden", "true");
    document.body.prepend(canvas);
    ctx = canvas.getContext("2d");
    rebuild();

    listen(document, "visibilitychange", function () {
      if (document.hidden) stopLoop(); else startLoop();
    });
    listen(window, "resize", function () {
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(rebuild, 150);
    });
    if (!reducedMotion()) {                       // user-tracking motion honors the OS pref
      listen(window, "scroll", function () {
        scrollOff = -Math.max(-MAX_PARALLAX_PX, Math.min(MAX_PARALLAX_PX, window.scrollY * 0.02));
      }, { passive: true });
      listen(window, "pointermove", function (e) {
        pointerX = ((e.clientX / Math.max(1, window.innerWidth)) - 0.5) * 2 * (MAX_PARALLAX_PX * 0.6);
      }, { passive: true });
    }
    startLoop();
  }
  function unmount() {
    stopLoop();
    clearTimeout(resizeTimer);
    for (var i = 0; i < teardownFns.length; i++) teardownFns[i]();
    teardownFns.length = 0;
    if (canvas && canvas.parentNode) canvas.parentNode.removeChild(canvas);
    canvas = null; ctx = null; stars.length = 0;
    scrollOff = 0; pointerX = 0;
  }
  function sync() {
    if (isDark()) { if (!canvas) mount(); }
    else if (canvas) unmount();
  }

  // ---- public API ----------------------------------------------------------
  window.EephusBG = {
    setFV: function (fv) {
      var t = (fv == null || !isFinite(fv)) ? 0
            : Math.max(0, Math.min(1, (fv - FV_FLOOR) / (FV_CEIL - FV_FLOOR)));
      this.setIntensity(t);
    },
    setIntensity: function (t) {
      t = Math.max(0, Math.min(1, +t || 0));
      if (t === fvT) return;
      fvT = t;
      if (canvas) rebuild();
    },
  };

  // ---- boot + theme gating -------------------------------------------------
  function boot() {
    sync();
    new MutationObserver(sync).observe(document.documentElement, {
      attributes: true, attributeFilter: ["data-theme"],
    });
  }
  if (document.body) boot();
  else document.addEventListener("DOMContentLoaded", boot);
})();
