/* Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
 * Unauthorized copying of this file, via any medium is strictly prohibited
 * Proprietary and confidential
 * Written by Noah J. Dengler (@ARKNDJL), 2026 */

// =============================================================================
// eephus.io player hub - cross-module identity + the unified share card
// =============================================================================
// One player exists on up to three card surfaces (PROSPX prospect card,
// FA market card, MLB player page). This tiny shared lib gives every
// surface the same two affordances:
//
//   EEPHUS_HUB.links()                  -> promise of data/player_links.json
//   EEPHUS_HUB.stripHTML(row, active)   -> the module hub strip (chips that
//                                          link the SAME player across
//                                          modules; active chip filled)
//   EEPHUS_HUB.shareCard(opts)          -> canvas-native PNG share card with
//                                          one visual language for every
//                                          module (module eyebrow + accent
//                                          carries the distinction)
//
// Canvas-native by the FA board precedent: html2canvas can't resolve CSS
// var(), hand-drawn cards are deterministic in both themes. Tokens are
// read from the live computed style at draw time.
(function () {
  "use strict";

  let _linksPromise = null;
  function links() {
    if (!_linksPromise) {
      _linksPromise = fetch("/data/player_links.json", { cache: "no-cache" })
        .then(r => (r.ok ? r.json() : null))
        .catch(() => null);
    }
    return _linksPromise;
  }

  function esc(s) {
    return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  // The module registry for the strip: id -> {label, glyph, href(row)}.
  // Module accents mirror the homepage sidebar glyph identity.
  const MODULES = [
    { id: "prospx", label: "PROSPX", glyph: "●", note: "prospect card",
      href: r => r.prospx ? `/prospx/#player=${encodeURIComponent(r.prospx)}` : null },
    { id: "fa", label: "FREE AGENCY", glyph: "$", note: "market card",
      href: r => r.fa ? `/fa/#player=${encodeURIComponent(r.key)}` : null },
    { id: "mlb", label: "MLB PROJECTIONS", glyph: "Δ", note: "player page",
      href: r => r.key ? `/projections/#player=${encodeURIComponent(r.key)}` : null },
  ];

  // row: {key, mlbam, fa, prospx} (a player_links entry). active: module id.
  function stripHTML(row, active) {
    if (!row) return "";
    const chips = MODULES.map(m => {
      const href = m.href(row);
      if (!href && m.id !== active) return "";
      const cls = m.id === active ? "hub-chip is-active" : "hub-chip";
      const inner = `<span class="hub-glyph">${m.glyph}</span>${m.label}<span class="hub-note">${m.note}</span>`;
      return m.id === active
        ? `<span class="${cls}" title="You are on this player's ${m.note}">${inner}</span>`
        : `<a class="${cls}" href="${href}" title="Open this player's ${m.note}">${inner}</a>`;
    }).filter(Boolean);
    if (chips.length <= 1) return "";
    return `<div class="player-hub-strip" title="One player, every module - the same player across eephus.io surfaces">${chips.join("")}</div>`;
  }

  // ---- unified share card ---------------------------------------------------
  function _tok(name, fallback) {
    const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    return v || fallback;
  }
  function _loadImage(url) {
    return new Promise(resolve => {
      if (!url) return resolve(null);
      const img = new Image();
      img.crossOrigin = "anonymous";
      img.onload = () => resolve(img);
      img.onerror = () => resolve(null);
      img.src = url;
    });
  }

  // opts: {module, accentToken?, name, meta, sub?, headshotURL?, url,
  //        filename, tiles: [{label, value, color?}] (<=4),
  //        sections: [{title, rows: [[label, value, color?], ...]}] (<=2),
  //        caption?}
  async function shareCard(opts) {
    const dark = document.documentElement.getAttribute("data-theme") === "dark";
    const W = 1200, H = 675, PAD = 48;
    const c = document.createElement("canvas");
    c.width = W; c.height = H;
    const g = c.getContext("2d");
    const bg = _tok("--bg-primary", dark ? "#101014" : "#F6F1E4");
    const bg2 = _tok("--bg-secondary", dark ? "#16161B" : "#EFE9D8");
    const fg = _tok("--text-primary", dark ? "#ECEEF2" : "#0F1B2D");
    const sub = _tok("--text-tertiary", dark ? "#7C808A" : "#706B5C");
    const line = _tok("--border", dark ? "#2B2B31" : "#C9C1AE");
    const accent = _tok(opts.accentToken || "--accent-cyan", dark ? "#00D9FF" : "#0E7C86");
    const MONO = '"MS Gothic","Osaka-Mono","Roboto Mono",monospace';
    g.fillStyle = bg; g.fillRect(0, 0, W, H);

    // header: brand + module eyebrow + date, iridescent rule under
    g.fillStyle = fg; g.font = `700 26px ${MONO}`;
    g.fillText("EEPHUS.IO", PAD, 52);
    g.fillStyle = accent; g.font = `700 22px ${MONO}`;
    g.fillText(String(opts.module || "").toUpperCase(), PAD + 190, 52);
    const today = new Date().toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
    g.fillStyle = sub; g.font = `15px ${MONO}`;
    g.fillText(today, W - PAD - g.measureText(today).width, 52);
    const ramp = g.createLinearGradient(PAD, 0, W - PAD, 0);
    (dark
      ? [[0, "#00D9FF"], [0.3, "#B47CFF"], [0.55, "#FF4FD8"], [0.78, "#FFD700"], [1, "#4FFF9E"]]
      : [[0, "#B91C1C"], [0.35, "#C9A227"], [0.65, "#1F7A3A"], [1, "#0E2B4D"]]
    ).forEach(([s, col]) => ramp.addColorStop(s, col));
    g.fillStyle = ramp; g.fillRect(PAD, 70, W - 2 * PAD, 3);

    // hero: headshot (when CORS lets us) + name + meta
    const img = await _loadImage(opts.headshotURL);
    let heroX = PAD;
    if (img) {
      const S = 132;
      g.save();
      g.fillStyle = bg2; g.fillRect(PAD, 100, S, S);
      g.drawImage(img, PAD, 100, S, S);
      g.strokeStyle = accent; g.lineWidth = 3;
      g.strokeRect(PAD, 100, S, S);
      g.restore();
      heroX = PAD + S + 26;
    }
    g.fillStyle = fg; g.font = `700 40px ${MONO}`;
    g.fillText(opts.name || "", heroX, 142);
    g.fillStyle = sub; g.font = `17px ${MONO}`;
    g.fillText(opts.meta || "", heroX, 174);
    if (opts.sub) {
      g.fillStyle = accent; g.font = `700 15px ${MONO}`;
      g.fillText(opts.sub, heroX, 202);
    }

    // tile rail (right-aligned over the hero band)
    const tiles = (opts.tiles || []).slice(0, 4);
    let tx = W - PAD;
    for (let i = tiles.length - 1; i >= 0; i--) {
      const t = tiles[i];
      g.font = `700 24px ${MONO}`;
      const vw = Math.max(g.measureText(String(t.value)).width, 86) + 28;
      tx -= vw;
      g.fillStyle = bg2; g.fillRect(tx, 96, vw, 64);
      g.strokeStyle = line; g.lineWidth = 1; g.strokeRect(tx, 96, vw, 64);
      g.fillStyle = sub; g.font = `700 11px ${MONO}`;
      g.fillText(String(t.label).toUpperCase(), tx + 12, 116);
      g.fillStyle = t.color || fg; g.font = `700 24px ${MONO}`;
      g.fillText(String(t.value), tx + 12, 146);
      tx -= 10;
    }

    // sections: up to two columns of label/value rows
    const secs = (opts.sections || []).slice(0, 2);
    const colW = (W - 2 * PAD - 36) / Math.max(1, secs.length);
    secs.forEach((s, si) => {
      const x = PAD + si * (colW + 36);
      let y = 268;
      g.fillStyle = sub; g.font = `700 14px ${MONO}`;
      g.fillText(String(s.title).toUpperCase(), x, y);
      g.strokeStyle = line; g.beginPath();
      g.moveTo(x, y + 10); g.lineTo(x + colW, y + 10); g.stroke();
      y += 44;
      (s.rows || []).slice(0, 8).forEach(([label, value, color]) => {
        g.fillStyle = sub; g.font = `15px ${MONO}`;
        g.fillText(String(label), x, y);
        g.fillStyle = color || fg; g.font = `700 17px ${MONO}`;
        const v = String(value);
        g.fillText(v, x + colW - g.measureText(v).width, y);
        y += 36;
      });
    });

    // footer: caption + url left, watermark right
    if (opts.caption) {
      g.fillStyle = sub; g.font = `13px ${MONO}`;
      g.fillText(opts.caption, PAD, H - 56);
    }
    g.fillStyle = fg; g.font = `700 16px ${MONO}`;
    g.fillText(opts.url || "eephus.io", PAD, H - 28);
    g.fillStyle = sub; g.font = `700 13px ${MONO}`;
    const wm = "eephus.io";
    g.fillText(wm, W - PAD - g.measureText(wm).width, H - 28);

    return new Promise(resolve => {
      c.toBlob(blob => {
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = opts.filename || "eephus-player-card.png";
        a.click();
        setTimeout(() => URL.revokeObjectURL(a.href), 5000);
        resolve(true);
      }, "image/png");
    });
  }

  window.EEPHUS_HUB = { links, stripHTML, shareCard, esc };
})();
