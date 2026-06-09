// eephus.io — dark-theme phosphor starfield background (shared component).
// Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
//
// One fixed, full-viewport <canvas id="eephus-bg"> behind all content, on BOTH
// surfaces (editorial pages + the PROSPX app). The radial glow + corner
// vignette are CSS background layers on the element itself (assets/site.css,
// dark scope); this module draws only the stars — faint green/amber phosphor
// points with a fast-brighten / slow-decay twinkle, like persistence on a CRT.
// Every dial lives in the [data-theme="dark"] token block in site.css.
//
// Dark-theme gating: a MutationObserver on <html data-theme> mounts the canvas
// when the dark theme activates and FULLY tears it down (animation frame,
// listeners, DOM node) on any other theme — this also catches programmatic
// flips like the Generate GFX modal's theme override, not just the toggles.
// Under any non-dark theme this module renders nothing and costs nothing.
//
// Hard guardrails (constants, deliberately NOT dialable via tokens):
//   • exactly one requestAnimationFrame loop, paused while document.hidden
//   • absolute star-count ceiling regardless of viewport size
//   • devicePixelRatio capped at 2
//   • prefers-reduced-motion: reduce → one static draw, no loop, no parallax
//   • parallax is scroll/pointer-driven only, capped at a few px — no
//     autonomous motion ("breathing" glow is a deliberate non-goal)
//
// FV linkage (PROSPX prospect views): the app calls EephusBG.setFV(fv) on
// route changes. Intensity t = clamp((fv - 45) / (70 - 45), 0, 1) — the floor
// and ceiling are the audited card-rarity thresholds (rankNumRarityClass in
// prospx/index.html: 45 shine … 70 legendary), NOT a parallel breakpoint set.
// Below the lowest tier (and on list views / editorial pages) → base field.
(function () {
  "use strict";

  var MAX_STARS = 240;        // absolute ceiling, any viewport, any FV
  var MAX_DPR = 2;            // retina fill-cost bound
  var MAX_PARALLAX_PX = 6;    // total drift budget at the deepest layer
  var FV_FLOOR = 45;          // rankNumRarityClass: lowest rarity tier (shine)
  var FV_CEIL = 70;           // rankNumRarityClass: top rarity tier (legendary)
  var LAYER_DEPTHS = [0.35, 0.65, 1.0];

  var canvas = null, ctx = null, rafId = null;
  var stars = [];             // {fx, fy, size, layer, hue(0|1), dim, period, phase}
  var tokens = null;          // parsed CSS token values (read at mount)
  var fvT = 0;                // 0..1 FV intensity (remembered across mounts)
  var scrollOff = 0, pointerX = 0, pointerY = 0;
  var teardownFns = [];       // listener removers registered by mount()
  var resizeTimer = null;

  var reducedMq = window.matchMedia ? window.matchMedia("(prefers-reduced-motion: reduce)") : null;
  function reducedMotion() { return !!(reducedMq && reducedMq.matches); }
  function isDark() { return document.documentElement.getAttribute("data-theme") === "dark"; }

  // ---- token plumbing ------------------------------------------------------
  function cssNum(styles, name, fallback) {
    var v = parseFloat(styles.getPropertyValue(name));
    return isFinite(v) ? v : fallback;
  }
  // Custom properties come back var()-substituted, so the color tokens resolve
  // to literal hex/rgb here. Parse both; fall back to the audited dark accents.
  function cssColor(styles, name, fallback) {
    var raw = (styles.getPropertyValue(name) || "").trim();
    var m = /^#([0-9a-f]{6})$/i.exec(raw);
    if (m) {
      var n = parseInt(m[1], 16);
      return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
    }
    m = /^#([0-9a-f]{3})$/i.exec(raw);
    if (m) {
      return [parseInt(m[1][0] + m[1][0], 16), parseInt(m[1][1] + m[1][1], 16), parseInt(m[1][2] + m[1][2], 16)];
    }
    m = /^rgba?\(\s*(\d+)[,\s]+(\d+)[,\s]+(\d+)/i.exec(raw);
    if (m) return [+m[1], +m[2], +m[3]];
    return fallback;
  }
  function readTokens() {
    var s = getComputedStyle(document.documentElement);
    tokens = {
      primary:     cssColor(s, "--star-color-primary",   [79, 255, 158]),  // refractor mint
      secondary:   cssColor(s, "--star-color-secondary", [255, 215, 0]),   // refractor gold
      mixRatio:    cssNum(s, "--star-mix-ratio", 0.85),
      density:     cssNum(s, "--star-density-base", 0.08),
      opacityMax:  cssNum(s, "--star-opacity-max", 0.45),
      speed:       cssNum(s, "--star-twinkle-speed", 1) || 1,
      attack:      Math.min(0.9, Math.max(0.02, cssNum(s, "--star-twinkle-attack", 0.18))),
      layers:      Math.max(2, Math.min(3, Math.round(cssNum(s, "--star-parallax-layers", 3)))),
      densityMult: cssNum(s, "--star-fv-density-mult", 1.6),
      chromaMult:  cssNum(s, "--star-fv-chroma-mult", 1.5),
      opacityMult: cssNum(s, "--star-fv-opacity-mult", 1.25),
    };
  }

  // Phosphor chroma: stars sit partway between a desaturated gray-green and the
  // full accent; FV intensity pulls them toward full saturation (chromaMult).
  function hueStyles() {
    var sat = Math.min(1, 0.55 * (1 + (tokens.chromaMult - 1) * fvT));
    function mix(c) {
      var avg = (c[0] + c[1] + c[2]) / 3;
      var r = Math.round(avg + (c[0] - avg) * sat);
      var g = Math.round(avg + (c[1] - avg) * sat);
      var b = Math.round(avg + (c[2] - avg) * sat);
      return "rgb(" + r + "," + g + "," + b + ")";
    }
    return [mix(tokens.primary), mix(tokens.secondary)];
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
      var layer = i % tokens.layers;
      stars.push({
        fx: Math.random(),
        fy: Math.random(),
        // deeper layers render smaller — cheap depth cue, all sharp squares
        size: layer === tokens.layers - 1 ? 2 : 1,
        layer: layer,
        hue: Math.random() < tokens.mixRatio ? 0 : 1,
        dim: 0.55 + Math.random() * 0.45,
        period: (2800 + Math.random() * 4200) / tokens.speed,
        phase: Math.random(),
      });
    }
  }

  // Phosphor envelope: linear fast rise over the attack fraction of the cycle,
  // then exponential decay (bright drop, long tail) — never a global pulse,
  // each star keeps its own random phase + period.
  function brightness(star, now) {
    var p = (now / star.period + star.phase) % 1;
    if (p < tokens.attack) return p / tokens.attack;
    return Math.exp(-3.2 * (p - tokens.attack) / (1 - tokens.attack));
  }

  function draw(now) {
    var w = canvas.clientWidth, h = canvas.clientHeight;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    var styles = hueStyles();
    var alphaMax = Math.min(0.7, tokens.opacityMax * (1 + (tokens.opacityMult - 1) * fvT));
    var dpr = canvas.width / Math.max(1, w);
    var stat = reducedMotion();
    for (var hue = 0; hue < 2; hue++) {
      ctx.fillStyle = styles[hue];
      for (var i = 0; i < stars.length; i++) {
        var st = stars[i];
        if (st.hue !== hue) continue;
        var b = stat ? st.phase : brightness(st, now);
        ctx.globalAlpha = alphaMax * st.dim * (0.12 + 0.88 * b);
        var depth = LAYER_DEPTHS[st.layer] || 1;
        var x = (st.fx * w + (pointerX * depth)) % w; if (x < 0) x += w;
        var y = (st.fy * h + (scrollOff * depth)) % h; if (y < 0) y += h;
        var s = st.size * dpr;
        ctx.fillRect(Math.round(x * dpr), Math.round(y * dpr), s, s);
      }
    }
    ctx.globalAlpha = 1;
  }

  // ---- the one animation loop ----------------------------------------------
  function frame(now) {
    rafId = null;
    if (!canvas) return;
    draw(now);
    if (!reducedMotion() && !document.hidden) rafId = requestAnimationFrame(frame);
  }
  function startLoop() {
    if (!canvas || rafId !== null) return;
    if (reducedMotion()) { draw(performance.now()); return; }  // static field
    if (!document.hidden) rafId = requestAnimationFrame(frame);
  }
  function stopLoop() {
    if (rafId !== null) { cancelAnimationFrame(rafId); rafId = null; }
  }

  // ---- mount / unmount -----------------------------------------------------
  function listen(target, ev, fn, opts) {
    target.addEventListener(ev, fn, opts);
    teardownFns.push(function () { target.removeEventListener(ev, fn, opts); });
  }
  function sizeCanvas() {
    var dpr = Math.min(MAX_DPR, window.devicePixelRatio || 1);
    var w = window.innerWidth, h = window.innerHeight;
    canvas.width = Math.round(w * dpr);
    canvas.height = Math.round(h * dpr);
  }
  function rebuild() {
    if (!canvas) return;
    sizeCanvas();
    buildStars(canvas.clientWidth || window.innerWidth, canvas.clientHeight || window.innerHeight);
    if (reducedMotion() || document.hidden) draw(performance.now());
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
      if (document.hidden) stopLoop(); else startLoop();   // zero cost on hidden tabs
    });
    listen(window, "resize", function () {
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(rebuild, 150);
    });
    if (!reducedMotion()) {
      listen(window, "scroll", function () {
        scrollOff = -Math.max(-MAX_PARALLAX_PX, Math.min(MAX_PARALLAX_PX, window.scrollY * 0.02));
      }, { passive: true });
      listen(window, "pointermove", function (e) {
        pointerX = ((e.clientX / Math.max(1, window.innerWidth)) - 0.5) * 2 * (MAX_PARALLAX_PX * 0.6);
      }, { passive: true });
    }
    if (reducedMq) {
      // re-arm or freeze if the OS motion preference flips mid-session
      var onMqChange = function () { stopLoop(); rebuild(); startLoop(); };
      if (reducedMq.addEventListener) listen(reducedMq, "change", onMqChange);
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
  // setFV is remembered even while unmounted (light theme), so toggling into
  // dark on an open prospect page picks up the right intensity immediately.
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
