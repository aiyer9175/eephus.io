// eephus.io - dark-theme starfield background (shared component).
// Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
//
// One fixed, full-viewport <canvas id="eephus-bg"> behind all content, on BOTH
// surfaces (editorial pages + the PROSPX app). The radial glow + corner vignette
// are CSS background layers on the element itself (assets/site.css, dark scope);
// this module draws the stars: a real night sky - a spread of magnitudes (a few
// bright, many faint), a spread of color temperature (mostly cool white, some
// blue-white, a few warm amber, and a small minority in the brand mint/gold so
// the field still ties to the Topps-Chrome refractor theme), each twinkling at
// its own rate and phase. Elegant and recessive: it stays a background.
//
// Dark-theme gating: a MutationObserver on <html data-theme> mounts the canvas
// when the dark theme activates and FULLY tears it down (animation frame,
// listeners, DOM node) on any other theme - this also catches programmatic flips
// like the Generate GFX modal's theme override, not just the toggles. Under any
// non-dark theme this module renders nothing and costs nothing.
//
// Hard guardrails (constants, deliberately NOT dialable via tokens):
//   • exactly one requestAnimationFrame loop, paused while document.hidden
//   • absolute star-count ceiling regardless of viewport size
//   • devicePixelRatio capped at 2
//   • prefers-reduced-motion: reduce → greatly reduced twinkle (near-static),
//     no parallax (this REPLACES the old FORCE_TWINKLE override; the owner ask
//     for the real starfield is to respect the OS motion preference - one
//     constant, REDUCED_TWINKLE_AMP, makes it reversible)
//   • parallax is scroll/pointer-driven only, capped at a few px; autonomous
//     drift is a token dial (--star-drift), off by default
//
// FV linkage (PROSPX prospect views): the app calls EephusBG.setFV(fv) on route
// changes. Intensity t = clamp((fv - 45) / (70 - 45), 0, 1) - the floor and
// ceiling are the audited card-rarity thresholds (rankNumRarityClass in
// prospx/index.html: 45 shine … 70 legendary), NOT a parallel breakpoint set.
// Higher t = a richer field: more stars, brighter, more brand-tinted. Below the
// lowest tier (and on list views / editorial pages) → base field.
(function () {
  "use strict";

  var MAX_STARS = 240;        // absolute ceiling, any viewport, any FV
  var MAX_DPR = 2;            // retina fill-cost bound
  var MAX_PARALLAX_PX = 6;    // total scroll/pointer drift budget at the deepest layer
  var FV_FLOOR = 45;          // rankNumRarityClass: lowest rarity tier (shine)
  var FV_CEIL = 70;           // rankNumRarityClass: top rarity tier (legendary)
  var LAYER_DEPTHS = [0.4, 0.7, 1.0];
  var REDUCED_TWINKLE_AMP = 0.06;  // twinkle amplitude ceiling under reduced-motion

  var canvas = null, ctx = null, rafId = null;
  var stars = [];             // see buildStars() for the shape
  var tokens = null;          // parsed CSS token values (read at mount)
  var fvT = 0;                // 0..1 FV intensity (remembered across mounts)
  var scrollOff = 0, pointerX = 0, pointerY = 0;
  var driftPhase = 0;         // autonomous drift accumulator (token-gated)
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
      // naturalistic temperature palette
      cool:        cssColor(s, "--star-color-cool",      [234, 241, 255]),  // cool white
      blue:        cssColor(s, "--star-color-blue",      [191, 212, 255]),  // blue-white
      warm:        cssColor(s, "--star-color-warm",      [255, 230, 184]),  // warm amber
      // brand-tinted minority (refractor mint + gold)
      brandA:      cssColor(s, "--star-color-primary",   [79, 255, 158]),
      brandB:      cssColor(s, "--star-color-secondary", [255, 215, 0]),
      brandRatio:  cssNum(s, "--star-brand-ratio", 0.16),
      density:     cssNum(s, "--star-density-base", 0.10),
      opacityMax:  cssNum(s, "--star-opacity-max", 0.5),
      speed:       cssNum(s, "--star-twinkle-speed", 1) || 1,
      layers:      Math.max(2, Math.min(3, Math.round(cssNum(s, "--star-parallax-layers", 3)))),
      drift:       Math.max(0, cssNum(s, "--star-drift", 0)),
      densityMult: cssNum(s, "--star-fv-density-mult", 1.6),
      chromaMult:  cssNum(s, "--star-fv-chroma-mult", 1.5),
      opacityMult: cssNum(s, "--star-fv-opacity-mult", 1.25),
    };
  }

  // ---- star field ----------------------------------------------------------
  function targetCount(w, h) {
    var density = tokens.density * (1 + (tokens.densityMult - 1) * fvT);
    return Math.min(MAX_STARS, Math.round((w * h) / 1000 * density));
  }
  // Pick a star color. A weighted draw over the temperature buckets, plus a
  // small brand-tinted minority whose share grows with FV intensity (chromaMult).
  function pickColor(r) {
    var brand = Math.min(0.6, tokens.brandRatio * (1 + (tokens.chromaMult - 1) * fvT));
    if (r < brand) return (r < brand * 0.55) ? tokens.brandA : tokens.brandB;
    var t = (r - brand) / (1 - brand);   // 0..1 across the natural buckets
    if (t < 0.70) return tokens.cool;     // mostly cool white
    if (t < 0.90) return tokens.blue;     // some blue-white
    return tokens.warm;                   // a few warm amber
  }
  function buildStars(w, h) {
    var n = targetCount(w, h);
    stars.length = 0;
    for (var i = 0; i < n; i++) {
      // Magnitude: cube of a uniform skews most stars faint/small, a few bright.
      var u = Math.random();
      var mag = u * u * u;                       // 0 faint .. 1 bright
      var layer = i % tokens.layers;
      // Bright stars twinkle less (like the real sky); faint ones shimmer more,
      // but most stars barely move - amplitude is small and varied.
      var amp = (0.06 + Math.random() * 0.30) * (1 - 0.5 * mag);
      stars.push({
        fx: Math.random(),
        fy: Math.random(),
        radius: 0.5 + mag * 1.9 + (layer === tokens.layers - 1 ? 0.3 : 0),
        baseB: 0.35 + 0.6 * mag + Math.random() * 0.1,   // base brightness
        color: pickColor(Math.random()),
        bright: mag > 0.78,                              // gets a soft halo
        twAmp: amp,
        twPeriod: (2600 + Math.random() * 5200) / tokens.speed,
        twPhase: Math.random(),
        layer: layer,
      });
    }
  }

  // Gentle twinkle: a smooth shimmer at the star's own rate/phase, never a
  // global pulse. Bright stars sit near full; faint ones breathe a little.
  function brightness(star, now, ampCeil) {
    var amp = Math.min(star.twAmp, ampCeil);
    var s = 0.5 + 0.5 * Math.sin(6.2831853 * (now / star.twPeriod + star.twPhase));
    return star.baseB * (1 - amp + amp * s);
  }

  function draw(now) {
    var w = canvas.clientWidth, h = canvas.clientHeight;
    var dpr = canvas.width / Math.max(1, w);
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    var alphaMax = Math.min(0.78, tokens.opacityMax * (1 + (tokens.opacityMult - 1) * fvT));
    var ampCeil = reducedMotion() ? REDUCED_TWINKLE_AMP : 1;
    var driftX = 0, driftY = 0;
    if (tokens.drift > 0 && !reducedMotion()) {
      driftX = Math.cos(driftPhase) * tokens.drift;
      driftY = Math.sin(driftPhase * 0.6) * tokens.drift * 0.5;
    }
    for (var i = 0; i < stars.length; i++) {
      var st = stars[i];
      var depth = LAYER_DEPTHS[st.layer] || 1;
      var b = brightness(st, now, ampCeil);
      var a = alphaMax * Math.max(0, Math.min(1, b));
      if (a < 0.01) continue;
      var x = (st.fx * w + pointerX * depth + driftX * depth) % w; if (x < 0) x += w;
      var y = (st.fy * h + scrollOff * depth + driftY * depth) % h; if (y < 0) y += h;
      var px = x * dpr, py = y * dpr, r = st.radius * dpr;
      var col = st.color;
      var rgb = col[0] + "," + col[1] + "," + col[2];
      if (st.bright) {
        // soft halo for the few bright stars
        ctx.fillStyle = "rgba(" + rgb + "," + (a * 0.16).toFixed(3) + ")";
        ctx.beginPath(); ctx.arc(px, py, r * 2.6, 0, 6.2831853); ctx.fill();
      }
      ctx.fillStyle = "rgba(" + rgb + "," + a.toFixed(3) + ")";
      ctx.beginPath(); ctx.arc(px, py, r, 0, 6.2831853); ctx.fill();
    }
  }

  // ---- the one animation loop ----------------------------------------------
  function frame(now) {
    rafId = null;
    if (!canvas) return;
    if (tokens.drift > 0) driftPhase += 0.0009;
    draw(now);
    if (!document.hidden) rafId = requestAnimationFrame(frame);
  }
  function startLoop() {
    if (!canvas || rafId !== null) return;
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
