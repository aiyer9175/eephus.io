/* Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
 * Unauthorized copying of this file, via any medium is strictly prohibited
 * Proprietary and confidential
 * Written by Noah J. Dengler (@ARKNDJL), 2026 */

// =============================================================================
// eephus.io - Franchises (/franchise/)
// =============================================================================
// Renders data/franchise_board.json (franchise_export.py): one page per club,
// re-serving what every module already publishes, on the scale it was computed
// on, each number labelled and linked back to the module that owns it. The
// organisational grade tree is the PROSPX farm tree ported under the .fr-
// prefix: a root card, a canopy (three graded bubbles, nine descriptive
// nameplates), the full three-column SVG, and the accordion below 1100px.
//
// FOUR RULES THIS FILE KEEPS.
//   1. Only a SCORE takes a colour. A branch score and the Franchise Index are
//      100+10z across the 30 clubs and take the `z` ladder from EephusTiers; a
//      LETTER prints in neutral ink and is never tiered, so a rank letter and a
//      score colour cannot disagree on one cell. An idx leaf takes the ladder
//      the payload names; a salary, a surplus total, a cap-space cell, a park
//      factor and a style z-score take no ladder, ever.
//   2. branchSpecs are BUILT FROM THE PAYLOAD (clubs[i].tree.branches), never
//      typed here; the weights print from DATA.weights.
//   3. ou_mkt and ou_war are two tiles and nothing here adds them; the DUGOUT
//      and MARKET sections carry no letter and no plus metric.
//   4. ODDS takes its verdict chip from the playoff_odds_sim registry row like
//      every other section, and prints the artifact's own interval sentence.
//
// NOT ONE FIGURE IN THIS FILE IS TYPED. Every number, basis and sentence comes
// out of the payload's own `copy`, `field_key` and per-club blocks. Colour
// comes from EephusTiers only: no hsl colour and no hex literal lives here.
(function () {
  "use strict";

  var DATA_URL = "/data/franchise_board.json";
  // QCLP10: each club's tree and sections live in its own file, fetched when
  // the club is shown (the board is a tenth of the size it was). A board that
  // still carries them inline renders with no second fetch.
  var SHARD_URL = "/data/franchise_clubs/";
  var SHARD_STATE = {};     // code -> "loading" | "failed"
  var DATA = null;
  var LOAD_ERROR = "";
  var CLUBS = {};
  var state = { view: "club", team: "", tree: "canopy", sec: "", treeSet: false,
                sort: { key: "index_score", asc: false } };

  // ---- helpers --------------------------------------------------------------
  function esc(s) {
    return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }
  // The pixel state box (assets/eephus-state.js, final-pass plan 5.7 PX-12):
  // loading, empty, unmeasured or failed, around a message this file escapes.
  // The bare box is the fallback for a test harness that loads this file alone.
  function pxState(kind, msg, opts) {
    var S = typeof window !== "undefined" && window.EephusState;
    if (S) return S.html(kind, msg, opts);
    var cls = typeof opts === "string" ? opts : (opts && opts.cls) || "";
    return '<div class="px-state is-' + kind + (cls ? " " + cls : "") + '"' +
      (kind === "failed" ? ' role="alert"' : "") + '><div class="px-state-msg">' + msg + "</div></div>";
  }
  function isNum(v) { return v !== null && v !== undefined && v === v && v !== "" && isFinite(Number(v)); }
  // a value that rounds to zero prints 0.0, never -0.0 (QCLC10: an ARB 3 WAR of -0.02 printed "-0.0")
  function n1(v) { if (!isNum(v)) return ""; var s = Number(v).toFixed(1); return s === "-0.0" ? "0.0" : s; }
  function n2(v) { return isNum(v) ? Number(v).toFixed(2) : ""; }
  function nInt(v) { return isNum(v) ? String(Math.round(Number(v))) : ""; }
  function pct(v, nd) { return isNum(v) ? (Number(v) * 100).toFixed(nd === undefined ? 1 : nd) + "%" : ""; }
  function pct3(v) { return isNum(v) ? Number(v).toFixed(3).replace(/^0/, "") : ""; }
  function signed(v, nd) { return isNum(v) ? (Number(v) > 0 ? "+" : "") + Number(v).toFixed(nd === undefined ? 1 : nd) : ""; }
  function money(usd) {
    if (!isNum(usd)) return "";
    var v = Number(usd) / 1e6;
    return (v < 0 ? "-" : "") + "$" + Math.abs(v).toFixed(1) + "M";
  }
  function moneyMM(mm) { return isNum(mm) ? (mm < 0 ? "-" : "") + "$" + Math.abs(Number(mm)).toFixed(1) + "M" : ""; }
  function el(id) { return document.getElementById(id); }
  function gl(label, id) {
    return '<a class="g-term" href="/glossary/#g=' + esc(id) + '" data-gl="' + esc(id) + '">' + esc(label) + "</a>";
  }
  function copy(k) { return (DATA && DATA.copy && DATA.copy[k]) || ""; }
  // One reader sentence from a copy fragment: a leading lower-case letter is
  // capitalised and a closing stop is added when the fragment has none, so
  // fragments joined into one note never read as a run-on (QCLC16, M09-12).
  function sentence(s) {
    var t = String(s == null ? "" : s).replace(/\s+$/, "").replace(/^\s+/, "");
    if (!t) return "";
    t = t.charAt(0).toUpperCase() + t.slice(1);
    return /[.!?:]$/.test(t) ? t : t + ".";
  }
  function prose() {
    return Array.prototype.map.call(arguments, function (s) { return esc(sentence(s)); })
      .filter(function (s) { return s; }).join(" ");
  }
  function signCls(v) {
    if (!isNum(v) || Number(v) === 0) return "";
    return Number(v) > 0 ? "fr-pos" : "fr-neg";
  }
  function signedMoney(usd) { return '<span class="' + signCls(usd) + '">' + money(usd) + "</span>"; }
  // THE RULER. Colour only (the display type owns its weight); family named by
  // the caller from the payload's `ladder`, never guessed here.
  function tierInk(v, fam) {
    try {
      if (fam && typeof EephusTiers !== "undefined" && EephusTiers && EephusTiers.clsInk) return EephusTiers.clsInk(v, fam);
    } catch (e) { /* ruler optional */ }
    return "";
  }
  function tierVar(v, fam) {
    try {
      if (fam && typeof EephusTiers !== "undefined" && EephusTiers && EephusTiers.varOf) return EephusTiers.varOf(v, fam) || "";
    } catch (e) { /* ruler optional */ }
    return "";
  }
  function scoreSpan(v) { return '<span class="' + tierInk(v, "z") + '">' + n1(v) + "</span>"; }
  function letterSpan(l) { return '<span class="fr-neutral">' + esc(l || "-") + "</span>"; }
  function dark(title, why) {
    return '<div class="fr-dark"><div><strong>' + esc(title) + '</strong><span class="fr-darktag">' + esc(copy("dark_tag")) + "</span></div>" +
      '<div class="fr-dark-why">' + esc(why) + "</div></div>";
  }
  function banner() { return '<div class="fr-banner" role="note">' + esc(copy("cba_banner")) + "</div>"; }
  function opt(v, label, cur) {
    return '<option value="' + esc(v) + '"' + (String(v) === String(cur) ? " selected" : "") + ">" + esc(label) + "</option>";
  }
  function clubOf(code) { return Object.prototype.hasOwnProperty.call(CLUBS, code) ? CLUBS[code] : null; }
  function hasBody(d) { return !!(d && d.tree && d.sections); }
  function loadShard(code) {
    var d = clubOf(code);
    // a failed file is not asked for again on the render that shows the
    // failure; picking the club again asks once more
    if (!d || hasBody(d) || SHARD_STATE[code]) return;
    SHARD_STATE[code] = "loading";
    var sh = DATA.shards || {}, stamp = (sh.files || {})[code];
    fetch(SHARD_URL + code + ".json" + (stamp ? "?v=" + stamp.sha256_16 : ""), { cache: "no-cache" })
      .then(function (r) { if (!r || !r.ok) throw new Error("shard"); return r.json(); })
      .then(function (s) {
        if (!s || s.code !== code) throw new Error("shard");
        (sh.keys || ["tree", "sections"]).forEach(function (k) { d[k] = s[k]; });
        delete SHARD_STATE[code];
        if (state.view === "club" && state.team === code) render();
      })
      .catch(function () {
        SHARD_STATE[code] = "failed";
        if (state.view === "club" && state.team === code) render();
      });
  }
  function codes() { return DATA ? DATA.codes.slice() : []; }
  function ensureTeam() {
    if (!state.team || !clubOf(state.team)) state.team = codes()[0] || "";
  }
  function wide() {
    try { return typeof window !== "undefined" && isNum(window.innerWidth) ? window.innerWidth >= 1100 : true; } catch (e) { return true; }
  }
  function branchOf(d, key) {
    var bs = d.tree.branches;
    for (var i = 0; i < bs.length; i++) if (bs[i].key === key) return bs[i];
    return null;
  }
  function weightPct(w) { return isNum(w) ? Math.round(Number(w) * 100) + "%" : ""; }

  // Every leaf prints the module's own number in the module's own format: the
  // `kind` enum comes from the payload's field_key and is never widened here.
  function fmtLeaf(lf) {
    var v = lf.value;
    switch (lf.kind) {
      case "war": return n1(v);
      case "idx": case "idx_plain": return nInt(v);
      case "pct": return pct(v, 1);
      case "pct3": return pct3(v);
      case "count": return nInt(v);
      case "usd": return money(v);
      case "usd_signed": return money(v);
      case "usdm": return moneyMM(v);
      case "num1": return n1(v);
      case "signed": return signed(v, 0);
      case "signed2": return signed(v, 2);
      case "plain": return isNum(v) ? String(v) : esc(v || "");
      case "dark": return copy("dark_tag");
      default: return v == null ? "" : String(v);
    }
  }
  function leafCls(lf) {
    if (lf.kind === "idx" || lf.kind === "war") return tierInk(lf.value, lf.ladder);
    if (lf.kind === "usd_signed" || lf.kind === "signed" || lf.kind === "signed2") return signCls(lf.value);
    return "";
  }

  // ---- hash router (mlbstats idiom: every key anchored to a separator) ------
  var VIEW_RE = /(?:^#|[#&])view=(board|club)\b/;
  var TEAM_RE = /(?:^#|[#&])team=([A-Z]{2,3})\b/;
  var TREE_RE = /(?:^#|[#&])tree=(hidden|canopy|full)\b/;
  var SEC_RE = /(?:^#|[#&])sec=([a-z_]+)\b/;
  function hashNow() {
    try { return (typeof location !== "undefined" && location.hash) || ""; } catch (e) { return ""; }
  }
  function readHash() {
    var h = hashNow();
    var v = VIEW_RE.exec(h);
    if (v) state.view = v[1];
    var t = TEAM_RE.exec(h);
    // Trusted only when it is a code the payload carries, so a hash can never
    // resolve a club off Object.prototype.
    if (t && DATA && clubOf(t[1])) {
      state.team = t[1];
      if (!v) state.view = "club";
    }
    var tr = TREE_RE.exec(h);
    if (tr) { state.tree = tr[1]; state.treeSet = true; }
    var s = SEC_RE.exec(h);
    state.sec = s && DATA && DATA.branch_order.indexOf(s[1]) >= 0 ? s[1] : "";
  }
  function writeHash() {
    var parts = ["view=" + state.view];
    if (state.view === "club" && state.team) {
      parts.push("team=" + state.team);
      if (state.treeSet) parts.push("tree=" + state.tree);
      if (state.sec) parts.push("sec=" + state.sec);
    }
    try {
      if (typeof history !== "undefined" && history.replaceState) history.replaceState(null, "", "#" + parts.join("&"));
      else if (typeof location !== "undefined") location.hash = "#" + parts.join("&");
    } catch (e) { /* hash is optional */ }
  }

  // ---- masthead -------------------------------------------------------------
  function boardRow(code) {
    var rows = (DATA && DATA.board) || [];
    for (var i = 0; i < rows.length; i++) if (rows[i].code === code) return rows[i];
    return {};
  }
  function renderMast(d) {
    // Before the club's file is in, the record comes off its board row, so the
    // masthead does not move when the sections land.
    var br = boardRow(d.code);
    var s = d.sections ? d.sections.season : { wins: br.wins_2026, losses: br.losses_2026 };
    var rec = isNum(s.wins) && isNum(s.losses) ? s.wins + "-" + s.losses : "";
    var rd = isNum(s.run_diff) ? ' <span class="' + signCls(s.run_diff) + '">' + signed(s.run_diff, 0) + "</span>" : "";
    var gfx = "";
    try { if (typeof window !== "undefined" && window.EEPHUS_GFX && window.EEPHUS_GFX.chipHTML) gfx = window.EEPHUS_GFX.chipHTML("fr-gfx"); } catch (e) { gfx = ""; }
    var sel = '<label>Club <select id="fr-club" class="eephus-select" data-team-picker aria-label="Club">' +
      codes().map(function (c) { var k = clubOf(c); return opt(c, c + (k && k.name ? " " + k.name : ""), state.team); }).join("") + "</select></label>";
    return '<div class="fr-mast">' +
      '<img class="fr-mast-logo" src="' + esc(d.logo) + '" alt="" loading="lazy">' +
      '<div><div class="fr-mast-name">' + esc(d.name) + '</div><div class="fr-mast-meta">' + esc(d.division || "") +
      (rec ? " &middot; " + esc(rec) + rd : "") + (isNum(s.division_rank) ? " &middot; " + gl("division rank", "season_record") + " " + esc(s.division_rank) : "") + "</div></div>" +
      '<div class="fr-mast-controls">' + sel + gfx + "</div></div>";
  }

  // ---- root card -------------------------------------------------------------
  function renderRoot(d) {
    var ix = d.index, W = DATA.weights;
    var graded = d.tree.branches.filter(function (b) { return b.kind === "graded"; });
    var foot = graded.map(function (b) {
      return esc(b.label) + " " + weightPct(W[b.key]) + (b.provisional ? " (" + esc(copy("outlook_chip")) + ")" : "");
    }).join(" &middot; ");
    return '<div class="fr-root" title="' + esc(copy("score_basis")) + '">' +
      '<div class="fr-root-eyebrow">' + gl(copy("root_eyebrow"), "franchise_index") + "</div>" +
      '<div class="fr-root-row"><span class="fr-root-letter">' + esc(ix.letter || "-") + "</span>" +
      '<span class="fr-root-rank">#' + esc(ix.rank) + " of " + esc(DATA.league.n) + "</span>" +
      '<span class="fr-root-score">' + scoreSpan(ix.score) + "</span></div>" +
      '<div class="fr-root-sentence">' + esc(copy("root_sentence")) + "</div>" +
      '<div class="fr-root-foot">' + foot + "<br>" + esc(copy("root_foot_descriptive")) + "</div></div>";
  }

  // ---- the canopy (root + three graded bubbles + nine nameplates) --------------
  function renderCanopy(d) {
    var W = 1180, PAD = 16, RIBBON = 26, ROOT_W = 180, ROOT_H = 116, R = 38, NP_H = 22, PL_W = 92, PL_H = 40;
    var graded = d.tree.branches.filter(function (b) { return b.kind === "graded"; });
    var desc = d.tree.branches.filter(function (b) { return b.kind === "descriptive"; });
    var top = PAD + RIBBON + 4;
    var yMid = top + ROOT_H / 2 + 6;
    var rootRight = PAD + ROOT_W;
    var areaL = rootRight + 60, areaR = W - PAD - 8, areaW = areaR - areaL;
    var yRow2 = yMid + R + 34;
    var H = yRow2 + PL_H + PAD + 10;
    var ix = d.index;
    var rootVar = tierVar(ix.score, "z") || "var(--text-tertiary)";
    var g = "";
    g += '<line class="fr-svg-rule" x1="' + PAD + '" y1="' + (PAD + 0.5) + '" x2="' + (W - PAD) + '" y2="' + (PAD + 0.5) + '" stroke-width="0.8" opacity="0.6"/>' +
      '<line class="fr-svg-rule" x1="' + PAD + '" y1="' + (PAD + 5.5) + '" x2="' + (W - PAD) + '" y2="' + (PAD + 5.5) + '" stroke-width="0.4" opacity="0.4"/>' +
      '<text class="fr-svg-text" x="' + (PAD + 4) + '" y="' + (PAD + 18) + '" style="font-size:10px;font-weight:700;letter-spacing:0.18em;text-transform:uppercase;fill:var(--text-tertiary)">' + esc(copy("canopy_eyebrow")) + "</text>" +
      '<text class="fr-svg-serif" x="' + (W - PAD - 4) + '" y="' + (PAD + 18) + '" text-anchor="end" style="font-style:italic;font-size:10px;fill:var(--text-tertiary)">' + esc(copy("canopy_right")) + "</text>" +
      '<line class="fr-svg-rule" x1="' + PAD + '" y1="' + (PAD + RIBBON - 1) + '" x2="' + (W - PAD) + '" y2="' + (PAD + RIBBON - 1) + '" stroke-width="0.4" opacity="0.4"/>';
    var rt = yMid - ROOT_H / 2;
    g += '<rect class="fr-svg-node" x="' + PAD + '" y="' + rt + '" width="' + ROOT_W + '" height="' + ROOT_H + '" stroke="' + rootVar + '" stroke-width="1"/>' +
      '<rect x="' + (PAD + 4) + '" y="' + (rt + 4) + '" width="' + (ROOT_W - 8) + '" height="' + (ROOT_H - 8) + '" fill="none" stroke="' + rootVar + '" stroke-width="0.6" opacity="0.55"/>' +
      '<text class="fr-svg-text" x="' + (PAD + ROOT_W / 2) + '" y="' + (rt + 18) + '" text-anchor="middle" style="font-size:9px;letter-spacing:0.18em;text-transform:uppercase;font-weight:700;fill:var(--text-tertiary)">' + esc(copy("root_eyebrow")) + "</text>" +
      '<text class="fr-svg-serif" x="' + (PAD + ROOT_W / 2) + '" y="' + (rt + 70) + '" text-anchor="middle" style="font-size:54px;font-weight:700">' + esc(ix.letter || "-") + "</text>" +
      '<text class="fr-svg-serif" x="' + (PAD + ROOT_W / 2) + '" y="' + (rt + 95) + '" text-anchor="middle" style="font-style:italic;font-size:11px;fill:var(--text-secondary)">#' + esc(ix.rank) + " of " + esc(DATA.league.n) + "</text>" +
      '<text class="fr-svg-mono" x="' + (PAD + ROOT_W / 2) + '" y="' + (rt + 108) + '" text-anchor="middle" style="font-size:9px;letter-spacing:0.06em;fill:' + rootVar + '">' + esc(n1(ix.score)) + "</text>";
    var n = graded.length;
    var step = areaW / n;
    graded.forEach(function (b, i) {
      var bx = areaL + step * i + step / 2;
      var v = tierVar(b.score, "z") || "var(--text-tertiary)";
      var npW = R * 2 + 36, npX = bx - npW / 2, npY = yMid - R - NP_H - 6;
      var midX = (rootRight + (bx - R)) / 2;
      g += '<path d="M ' + rootRight + " " + (yMid - 1.5) + " L " + midX + " " + (yMid - 1.5) + " L " + (bx - R) + " " + (yMid - 1.5) + '" fill="none" stroke="' + v + '" stroke-width="1.2" opacity="0.6"/>' +
        '<path d="M ' + rootRight + " " + (yMid + 1.5) + " L " + midX + " " + (yMid + 1.5) + " L " + (bx - R) + " " + (yMid + 1.5) + '" fill="none" stroke="' + v + '" stroke-width="0.6" opacity="0.4"/>';
      g += '<rect class="fr-svg-plate" x="' + npX + '" y="' + npY + '" width="' + npW + '" height="' + NP_H + '" stroke-width="0.8"/>' +
        '<text class="fr-svg-serif" x="' + bx + '" y="' + (npY + 14) + '" text-anchor="middle" style="font-size:11px;font-weight:700;letter-spacing:0.04em">' + esc(b.label) + "</text>" +
        '<circle class="fr-svg-node" cx="' + bx + '" cy="' + yMid + '" r="' + R + '" stroke="' + v + '" stroke-width="2.4"/>' +
        '<circle cx="' + bx + '" cy="' + yMid + '" r="' + (R - 4) + '" fill="none" stroke="' + v + '" stroke-width="0.5" opacity="0.45"/>' +
        '<text class="fr-svg-serif" x="' + bx + '" y="' + (yMid + 9) + '" text-anchor="middle" style="font-size:32px;font-weight:700">' + esc(b.letter || "-") + "</text>" +
        '<text class="fr-svg-mono" x="' + bx + '" y="' + (yMid + R + 14) + '" text-anchor="middle" style="font-size:9px">' + esc(weightPct(DATA.weights[b.key])) + " weight &middot; #" + esc(b.rank) + " of " + esc(DATA.league.n) + "</text>" +
        '<text class="fr-svg-mono" x="' + bx + '" y="' + (yMid + R + 25) + '" text-anchor="middle" style="font-size:9px;fill:' + v + '">' + esc(n1(b.score)) + "</text>";
      if (b.provisional) {
        // THE PROVISIONAL CHIP ON THE BUBBLE (owner decision D6 alternative).
        // 9px text (was 7px, under any reading size) on a 74 x 13 chip
        var cw = 74, cx = bx + R - 10, cy = yMid - R - 2;
        g += '<rect class="fr-svg-chip" x="' + (cx - cw / 2) + '" y="' + (cy - 7) + '" width="' + cw + '" height="13"/>' +
          '<text class="fr-svg-chip-text" x="' + cx + '" y="' + (cy + 3) + '" text-anchor="middle">' + esc(copy("outlook_chip")) + "</text>";
      }
    });
    var m = desc.length, pstep = areaW / m;
    desc.forEach(function (b, i) {
      var px = areaL + pstep * i + pstep / 2 - PL_W / 2;
      var midY = (yMid + R + 30 + yRow2) / 2;
      g += '<path d="M ' + (px + PL_W / 2) + " " + (yMid + R + 30) + " L " + (px + PL_W / 2) + " " + midY + '" fill="none" stroke="var(--text-tertiary)" stroke-width="0.5" opacity="0.4"/>';
      g += '<rect class="fr-svg-plate" x="' + px + '" y="' + yRow2 + '" width="' + PL_W + '" height="' + PL_H + '" stroke-width="0.6"/>' +
        '<text class="fr-svg-serif" x="' + (px + PL_W / 2) + '" y="' + (yRow2 + 15) + '" text-anchor="middle" style="font-size:9px;font-weight:700;letter-spacing:0.04em">' + esc(b.label) + "</text>" +
        '<text class="fr-svg-mono" x="' + (px + PL_W / 2) + '" y="' + (yRow2 + 30) + '" text-anchor="middle" style="font-size:8.5px;fill:var(--text-secondary)">' + esc(b.headline || "") + "</text>";
    });
    g += '<line class="fr-svg-rule" x1="' + areaL + '" y1="' + (yMid + R + 30) + '" x2="' + areaR + '" y2="' + (yMid + R + 30) + '" stroke-width="0.4" opacity="0.4"/>';
    return '<svg viewBox="0 0 ' + W + " " + H + '" role="img" aria-label="' + esc(d.name) + " franchise canopy: the index, three graded branches and nine descriptive branches" + '">' + g + "</svg>";
  }

  // ---- the full three-column tree, built from the payload's branches ----------
  function renderFullTree(d) {
    var LEAF_H = 24, LEAF_GAP = 2, GROUP_GAP = 10, LEAF_W = 250, BRANCH_R = 26, PLATE_W = 96, PLATE_H = 40;
    var ROOT_W = 134, ROOT_H = 78, PAD_T = 14, PAD_L = 10;
    var COL_ROOT_RIGHT = PAD_L + ROOT_W, COL_BRANCH_X = 252, COL_LEAF_LEFT = 358;
    var y = PAD_T;
    var layouts = d.tree.branches.map(function (b) {
      var leaves = b.leaves.map(function (lf) {
        var top = y, cy = y + LEAF_H / 2;
        y += LEAF_H + LEAF_GAP;
        return { leaf: lf, top: top, cy: cy };
      });
      var by = leaves.length ? (leaves[0].cy + leaves[leaves.length - 1].cy) / 2 : y;
      y += GROUP_GAP;
      return { b: b, leaves: leaves, by: by };
    });
    var H = y - GROUP_GAP + PAD_T, W = COL_LEAF_LEFT + LEAF_W + 160 + PAD_L, rootY = H / 2;
    var ix = d.index;
    var rootVar = tierVar(ix.score, "z") || "var(--text-tertiary)";
    var g = "";
    layouts.forEach(function (L) {
      var v = L.b.kind === "graded" ? (tierVar(L.b.score, "z") || "var(--text-tertiary)") : "var(--text-tertiary)";
      var midX = (COL_ROOT_RIGHT + (COL_BRANCH_X - BRANCH_R)) / 2;
      g += '<path d="M ' + COL_ROOT_RIGHT + " " + rootY + " L " + midX + " " + rootY + " L " + midX + " " + L.by + " L " + (COL_BRANCH_X - BRANCH_R) + " " + L.by + '" fill="none" stroke="' + v + '" stroke-width="2" opacity="0.75"/>';
      L.leaves.forEach(function (lp) {
        var mx = (COL_BRANCH_X + BRANCH_R + COL_LEAF_LEFT) / 2;
        g += '<path d="M ' + (COL_BRANCH_X + BRANCH_R) + " " + L.by + " L " + mx + " " + L.by + " L " + mx + " " + lp.cy + " L " + COL_LEAF_LEFT + " " + lp.cy + '" fill="none" stroke="' + v + '" stroke-width="1.5" opacity="0.55"/>';
      });
    });
    g += '<rect class="fr-svg-node" x="' + PAD_L + '" y="' + (rootY - ROOT_H / 2) + '" width="' + ROOT_W + '" height="' + ROOT_H + '" stroke="' + rootVar + '" stroke-width="2.2"/>' +
      '<text class="fr-svg-text" x="' + (PAD_L + ROOT_W / 2) + '" y="' + (rootY - 18) + '" text-anchor="middle" style="font-size:9px;letter-spacing:0.10em;text-transform:uppercase;font-weight:600;fill:var(--text-tertiary)">' + esc(copy("root_eyebrow")) + "</text>" +
      '<text class="fr-svg-serif" x="' + (PAD_L + ROOT_W / 2) + '" y="' + (rootY + 7) + '" text-anchor="middle" style="font-size:30px;font-weight:700">' + esc(ix.letter || "-") + "</text>" +
      '<text class="fr-svg-mono" x="' + (PAD_L + ROOT_W / 2) + '" y="' + (rootY + 24) + '" text-anchor="middle" style="font-size:10px;fill:var(--text-secondary)">#' + esc(ix.rank) + " of " + esc(DATA.league.n) + " &middot; " + esc(n1(ix.score)) + "</text>";
    layouts.forEach(function (L) {
      var b = L.b;
      if (b.kind === "graded") {
        var v = tierVar(b.score, "z") || "var(--text-tertiary)";
        g += '<circle class="fr-svg-node" cx="' + COL_BRANCH_X + '" cy="' + L.by + '" r="' + BRANCH_R + '" stroke="' + v + '" stroke-width="2.2"/>' +
          '<text class="fr-svg-serif" x="' + COL_BRANCH_X + '" y="' + (L.by - 3) + '" text-anchor="middle" style="font-size:17px;font-weight:700">' + esc(b.letter || "-") + "</text>" +
          '<text class="fr-svg-mono" x="' + COL_BRANCH_X + '" y="' + (L.by + 10) + '" text-anchor="middle" style="font-size:9px">' + esc(weightPct(DATA.weights[b.key])) + " &middot; #" + esc(b.rank) + "</text>" +
          '<text class="fr-svg-text" x="' + COL_BRANCH_X + '" y="' + (L.by - BRANCH_R - 4) + '" text-anchor="middle" style="font-size:10px;letter-spacing:0.04em;font-weight:600">' + esc(b.label) + (b.provisional ? " (" + esc(copy("outlook_chip")) + ")" : "") + "</text>";
      } else {
        g += '<rect class="fr-svg-plate" x="' + (COL_BRANCH_X - PLATE_W / 2) + '" y="' + (L.by - PLATE_H / 2) + '" width="' + PLATE_W + '" height="' + PLATE_H + '" stroke-width="0.8"/>' +
          '<text class="fr-svg-serif" x="' + COL_BRANCH_X + '" y="' + (L.by - 4) + '" text-anchor="middle" style="font-size:10px;font-weight:700;letter-spacing:0.04em">' + esc(b.label) + "</text>" +
          '<text class="fr-svg-mono" x="' + COL_BRANCH_X + '" y="' + (L.by + 11) + '" text-anchor="middle" style="font-size:8.5px;fill:var(--text-secondary)">' + esc(b.headline || "") + "</text>";
      }
      L.leaves.forEach(function (lp) {
        var lf = lp.leaf;
        var lv = (lf.kind === "idx" || lf.kind === "war") ? (tierVar(lf.value, lf.ladder) || "var(--text-tertiary)") : "var(--text-tertiary)";
        g += '<g><title>' + esc(lf.label + ": " + fmtLeaf(lf) + " (" + lf.basis + ")") + "</title>" +
          '<rect class="fr-svg-leaf" x="' + COL_LEAF_LEFT + '" y="' + lp.top + '" width="' + LEAF_W + '" height="' + LEAF_H + '" stroke-width="1"/>' +
          '<rect x="' + COL_LEAF_LEFT + '" y="' + lp.top + '" width="3" height="' + LEAF_H + '" fill="' + lv + '" opacity="0.95"/>' +
          '<text class="fr-svg-text" x="' + (COL_LEAF_LEFT + 10) + '" y="' + (lp.cy + 4) + '" style="font-size:10px;font-weight:600">' + esc(lf.label) + "</text>" +
          '<text class="fr-svg-mono" x="' + (COL_LEAF_LEFT + LEAF_W - 8) + '" y="' + (lp.cy + 4) + '" text-anchor="end" style="font-size:10px;font-weight:700;fill:' + lv + '">' + esc(fmtLeaf(lf)) + "</text></g>";
      });
    });
    return '<svg viewBox="0 0 ' + W + " " + H + '" role="img" aria-label="' + esc(d.name) + " franchise grade tree, every branch and leaf" + '">' + g + "</svg>";
  }

  function renderAccordion(d) {
    return '<div class="fr-tree-fallback">' + d.tree.branches.map(function (b, i) {
      var head = '<span class="fr-acc-label">' + esc(b.label) + '</span>' +
        (b.kind === "graded"
          ? '<span class="fr-acc-letter">' + esc(b.letter || "-") + '</span><span class="fr-acc-score">' + scoreSpan(b.score) + '</span>' +
            '<span class="fr-acc-meta">' + esc(weightPct(DATA.weights[b.key])) + " &middot; #" + esc(b.rank) + (b.provisional ? " &middot; " + esc(copy("outlook_chip")) : "") + "</span>"
          : '<span class="fr-acc-meta">' + esc(b.headline || "") + "</span>");
      var leaves = b.leaves.map(function (lf) {
        return "<li><span>" + (lf.gl ? gl(lf.label, lf.gl) : esc(lf.label)) + '</span><b class="' + leafCls(lf) + '" title="' + esc(lf.basis) + '">' + esc(fmtLeaf(lf)) + "</b></li>";
      }).join("");
      return '<details class="fr-acc"' + (i < 3 ? " open" : "") + "><summary>" + head + '</summary><ul class="fr-acc-leaves">' + leaves + "</ul></details>";
    }).join("") + "</div>";
  }

  function renderTree(d) {
    var mode = state.tree;
    function chip(val, lbl, tipKey) {
      // aria-pressed names the state the "active" class only paints (QCLA13).
      return '<button class="chip' + (mode === val ? " active" : "") + '" data-frtree="' + val + '" type="button" aria-pressed="' + (mode === val ? "true" : "false") + '" title="' + esc(copy(tipKey)) + '">' + lbl + "</button>";
    }
    var body = mode === "full" ? '<div class="fr-tree-svg">' + renderFullTree(d) + "</div>" : "";
    return '<div class="fr-tree-wrap"><div class="fr-tree-toggle" role="group" aria-label="Tree view"><span aria-hidden="true">Tree view</span>' +
      chip("hidden", "Hidden", "tree_hidden") + chip("canopy", "Canopy", "tree_canopy") + chip("full", "Full", "tree_full") +
      "</div>" + body + "</div>" + renderAccordion(d);
  }

  // ---- section plumbing -------------------------------------------------------
  var OPEN_LINKS = {
    roster: [["Hitters", "mlbstats_hitters"], ["Starters", "mlbstats_starters"], ["Bullpen", "mlbstats_bullpen"], ["Defense", "mlbstats_defense"], ["eWAR", "mlbstats_war"], ["Leverage", "mlbstats_leverage"]],
    season: [["Team board", "betting_teams"], ["Team Outlook", "team_outlook"]],
    outlook: [["Team Outlook", "team_outlook"], ["Roster board", "roster_board"]],
    farm: [["Farm page", "farm"], ["Tendencies", "tendencies"], ["Tree", "farm_tree"]],
    fin: [["Club Ledger", "ledger"], ["Trade board", "trade_board"]],
    market: [["FA fits", "fa_fits"], ["Archive", "fa_archive"]],
    front_office: [["Tendencies", "tendencies"], ["Draft", "draft_board"], ["IFA", "ifa_board"]],
    dugout: [["Club style", "management_club"]],
    arbitration: [["Club view", "arbitration_teams"], ["History", "arbitration_history"], ["Model", "arbitration_model"]],
    park: [["MiLB park factors", "parks"]],
    history: [["Hall of Fame", "hof"]],
    odds: [["Team board", "betting_teams"], ["Futures", "betting_futures"]]
  };
  function head(d, key) {
    var b = branchOf(d, key);
    var chip = b.verdict
      ? '<span class="eephus-beta fr-verdict" title="' + esc(b.basis) + '">' + esc(b.verdict_model) + " " + esc(b.verdict) + "</span>"
      : "";
    var links = (OPEN_LINKS[key] || []).map(function (p) {
      var href = d.links[p[1]];
      return href ? '<a href="' + esc(href) + '">' + esc(p[0]) + "</a>" : "";
    }).join("");
    // The status chip sits beside the heading, not inside it, so the heading's
    // name reads "ROSTER The major-league club today" and the chip is its own
    // text (QCLA13: the two ran together as "...todayewar provisional").
    return '<div class="fr-sec-head"><h2 id="fr-sec-' + esc(key) + '">' + esc(b.label) + ' <span class="fr-sec-title">' + esc(b.title) + "</span></h2>" + chip + "</div>" +
      '<div class="fr-basis">basis: ' + esc(b.basis) + "</div>" +
      '<div class="fr-open">' + esc(copy("open_in")) + " " + links + "</div>";
  }
  // NEVER A NESTED ANCHOR. The title may itself be a gl() term (an <a>), so
  // the tile is a <div> always and a deep link rides a trailing "open" chip:
  // an <a> inside an <a> is splintered by the HTML parser, which left the tile
  // box empty and its number floating beside it (review 2026-09-23).
  function tile(title, big, sub, cls, href) {
    var open = href ? '<a class="fr-tile-open" href="' + esc(href) + '">' + esc(copy("tile_open")) + "</a>" : "";
    return '<div class="fr-tile' + (href ? " fr-tile-linked" : "") + '"><div class="fr-tile-title">' + title + '</div><div class="fr-tile-big ' + (cls || "") + '">' + big +
      '</div><div class="fr-tile-sub">' + (sub || "") + "</div>" + open + "</div>";
  }
  // A tile names the board it quotes in words; the payload path rides the
  // title (X06-14: "hitter_leaderboards.teams.offense_plus" was reader copy).
  var BASIS_BOARD = { war: "eWAR", hitter: "Hitters", starter: "Starters", bullpen: "Bullpen", defense: "Defense", leverage: "Leverage" };
  function basisText(basis) {
    var s = String(basis == null ? "" : basis);
    var m = /^([a-z]+)_leaderboards\.teams\.[a-z_0-9]+(.*)$/.exec(s);
    return m && BASIS_BOARD[m[1]] ? "MLB Stats " + BASIS_BOARD[m[1]] + " team board" + m[2] : s;
  }
  function leafTile(lf, sub) {
    var basis = '<span title="' + esc(lf.basis) + '">' + esc(basisText(lf.basis)) + "</span>";
    return tile(lf.gl ? gl(lf.label, lf.gl) : esc(lf.label), esc(fmtLeaf(lf)), sub === undefined ? basis : sub, leafCls(lf), lf.link);
  }
  function leafBy(b, key) {
    for (var i = 0; i < b.leaves.length; i++) if (b.leaves[i].key === key) return b.leaves[i];
    return null;
  }
  function spark(points, zeroAt, label) {
    var xs = points.filter(function (p) { return isNum(p[1]); });
    if (xs.length < 2) return "";
    var W = 520, H = 36, lo = Infinity, hi = -Infinity;
    xs.forEach(function (p) { lo = Math.min(lo, Number(p[1])); hi = Math.max(hi, Number(p[1])); });
    if (isNum(zeroAt)) { lo = Math.min(lo, zeroAt); hi = Math.max(hi, zeroAt); }
    if (hi === lo) { hi = lo + 1; }
    function X(i) { return (i / (xs.length - 1) * (W - 4) + 2).toFixed(1); }
    function Y(v) { return (H - 3 - (Number(v) - lo) / (hi - lo) * (H - 6)).toFixed(1); }
    var pts = xs.map(function (p, i) { return X(i) + "," + Y(p[1]); }).join(" ");
    var dots = xs.map(function (p, i) { return '<circle cx="' + X(i) + '" cy="' + Y(p[1]) + '" r="2.5" fill="transparent"><title>' + esc(p[0] + ": " + p[1]) + "</title></circle>"; }).join("");
    var zero = isNum(zeroAt) ? '<line class="fr-spark-zero" x1="0" x2="' + W + '" y1="' + Y(zeroAt) + '" y2="' + Y(zeroAt) + '"/>' : "";
    // Named like the other strips (QCLA13): the first and last points ride the
    // name, and every point keeps its own <title>.
    function pt(p) { return p[0] + " " + (Number(p[1]) % 1 ? n1(p[1]) : String(p[1])); }
    var name = (label || "series") + ", " + pt(xs[0]) + " to " + pt(xs[xs.length - 1]);
    return '<div class="fr-spark"><svg viewBox="0 0 ' + W + " " + H + '" preserveAspectRatio="none" role="img" aria-label="' + esc(name) + '">' + zero + '<polyline class="fr-spark-line" points="' + pts + '"/>' + dots + "</svg></div>";
  }
  // A label/value table: the label cell is a row header (QCLA13).
  function mini(rows) {
    return '<table class="fr-mini">' + rows.map(function (r) { return '<tr><th scope="row">' + r[0] + "</th><td>" + r[1] + "</td></tr>"; }).join("") + "</table>";
  }
  function table(headers, rows, hideFrom) {
    var th = headers.map(function (h, i) { return '<th scope="col" class="' + (hideFrom !== undefined && i >= hideFrom ? "fr-col-hide" : "") + '">' + h + "</th>"; }).join("");
    var body = rows.map(function (r) {
      return "<tr>" + r.map(function (c, i) { return '<td class="' + (hideFrom !== undefined && i >= hideFrom ? "fr-col-hide" : "") + '">' + c + "</td>"; }).join("") + "</tr>";
    }).join("");
    return '<table class="fr-table"><thead><tr>' + th + "</tr></thead><tbody>" + body + "</tbody></table>";
  }
  function playerLink(name, key) {
    return key ? '<a href="/projections/#player=' + esc(key) + '">' + esc(name) + "</a>" : esc(name);
  }

  // ---- the twelve sections ----------------------------------------------------
  function secRoster(d) {
    var b = branchOf(d, "roster"), s = d.sections.roster;
    var tiles = b.leaves.map(function (lf) {
      return leafTile(lf, lf.key === "leverage_deploy_plus" ? esc(copy("leverage_deploy_note")) : undefined);
    }).join("");
    var split = mini([[gl("Hitters", "ewar"), n1(s.split.bat)], ["Starters", n1(s.split.sp)], ["Relievers", n1(s.split.rp)], ["Two-way", n1(s.split.sw)], ["Players on the board", nInt(s.n_players)]]);
    var lineup = table(["Lineup", gl("HEM+", "hem_plus"), "PA", "Bats", "Tier"], s.lineup.map(function (r) {
      return [esc(r[1]), '<span class="' + tierInk(r[3], "ratio") + '">' + nInt(r[3]) + "</span>", nInt(r[4]), esc(r[2] || ""), esc(r[0] || "")];
    }), 2);
    // SEM+ takes the run family, the one the /mlbstats/ rotation board paints it on.
    var rotation = table(["Rotation", gl("SEM+", "sem_plus"), "IP", "GS", "Role"], s.rotation.map(function (r) {
      return [esc(r[1]), '<span class="' + tierInk(r[2], "run") + '">' + nInt(r[2]) + "</span>", n1(r[3]), nInt(r[4]), esc(r[0] || "")];
    }), 2);
    var pen = table(["Bullpen", gl("REM+", "rem_plus"), "gmLI", "IP", "Role"], s.bullpen.map(function (r) {
      return [esc(r[1]), '<span class="' + tierInk(r[2], "run") + '">' + nInt(r[2]) + "</span>", n2(r[3]), n1(r[4]), esc(r[0] || "")];
    }), 2);
    var align = table(["Alignment", gl("DEM+", "dem_plus"), "Inn", "Frm", "Pos"], s.alignment.map(function (r) {
      return [esc(r[1]), '<span class="' + tierInk(r[2], "z") + '">' + nInt(r[2]) + "</span>", n1(r[3]), signed(r[4], 1), esc(r[0] || "")];
    }), 2);
    return '<div class="fr-tiles">' + tiles + "</div>" + '<p class="fr-count">' + prose(copy("roster_note")) + "</p>" +
      '<div class="fr-grid2"><div>' + split + "</div><div>" + lineup + "</div><div>" + rotation + "</div><div>" + pen + "</div><div>" + align + "</div></div>";
  }
  function secSeason(d) {
    var s = d.sections.season, b = branchOf(d, "season");
    var t = tile(gl("Record " + esc(DATA.season_now), "season_record"), esc(isNum(s.wins) ? s.wins + "-" + s.losses : ""), esc(nInt(s.games)) + " games", "", d.links.betting_teams) +
      tile("Run differential", '<span class="' + signCls(s.run_diff) + '">' + esc(signed(s.run_diff, 0)) + "</span>", esc(nInt(s.rs)) + " scored, " + esc(nInt(s.ra)) + " allowed") +
      tile("Division rank", esc(nInt(s.division_rank)), esc(d.division || "") + (s.division_champ ? " &middot; division champion" : s.clinched ? " &middot; clinched" : "")) +
      tile(gl("Pythag pct", "pythag_pct"), esc(pct3(s.pythag_pct)), "actual " + esc(pct3(s.actual_pct)) + " &middot; " + esc(copy("pythag_label")), "", d.links.team_outlook);
    return '<div class="fr-tiles">' + t + "</div>" + '<p class="fr-note">' + esc(copy("season_note")) + "</p>" +
      (isNum(s.gb) ? '<p class="fr-count">games back ' + esc(n1(s.gb)) + " &middot; remaining " + esc(nInt(s.rem_games)) + "</p>" : "");
  }
  function secOutlook(d) {
    var s = d.sections.outlook, b = branchOf(d, "outlook");
    var t = tile(gl("Wins " + esc(DATA.class_year), "franchise_branch_score") + '<span class="fr-chip-prov">' + esc(copy("outlook_chip")) + "</span>",
                 esc(n1(s.wins)), esc(n1(s.wins)) + "-" + esc(n1(s.losses)) + " &middot; " + esc(copy("outlook_note")), "", d.links.team_outlook) +
      tile("Roster WAR " + esc(DATA.class_year), esc(n1(s.war)), "depth " + esc(n1(s.depth_war)) + " &middot; " + esc(nInt(s.n_players)) + " players", "", d.links.roster_board) +
      tile(gl("Core under control", "locked_pct"), esc(pct(s.locked_pct, 0)), '<div class="fr-lock"><span style="width:' + (isNum(s.locked_pct) ? (Number(s.locked_pct) * 100).toFixed(1) : 0) + '%"></span></div>', "", d.links.roster_board) +
      tile("Controlled WAR, 5y", esc(n1(s.ctrl_war_5y)), "of " + esc(n1(s.full_war_5y)) + " projected");
    var W = 520, H = 72, n = s.by_year.length, hi = 0;
    s.by_year.forEach(function (y) { hi = Math.max(hi, Number(y[1]) || 0); });
    var bars = s.by_year.map(function (y, i) {
      var bw = (W - 20) / Math.max(n, 1), h = hi ? (Number(y[1]) / hi) * (H - 22) : 0, x = 10 + i * bw;
      return '<rect class="fr-bar" x="' + (x + 6) + '" y="' + (H - 14 - h) + '" width="' + (bw - 12) + '" height="' + h + '"><title>' + esc(y[0] + ": " + n1(y[1]) + " wins") + "</title></rect>" +
        '<text x="' + (x + bw / 2) + '" y="' + (H - 3) + '" text-anchor="middle">' + esc(y[0]) + "</text>" +
        '<text x="' + (x + bw / 2) + '" y="' + (H - 18 - h) + '" text-anchor="middle">' + esc(n1(y[1])) + "</text>";
    }).join("");
    var strip = '<div class="fr-strip"><svg viewBox="0 0 ' + W + " " + H + '" role="img" aria-label="projected wins by season">' + bars + "</svg></div>";
    var top = s.top.map(function (p) { return "<li>" + playerLink(p[0], p[1]) + " " + esc(n1(p[2])) + " WAR</li>"; }).join("");
    return '<div class="fr-tiles">' + t + "</div>" + strip + "<ul>" + top + "</ul>" +
      '<p class="fr-count">' + esc(copy("outlook_accounting")) + "</p>";
  }
  function secFarm(d) {
    var s = d.sections.farm, b = branchOf(d, "farm");
    var t = tile("PROSPX letter", letterSpan(s.letter), "#" + esc(s.rank) + " of " + esc(DATA.league.n) + " &middot; farm_score " + esc(n1(s.farm_score)), "", d.links.farm) +
      tile(gl("Branch score", "franchise_branch_score"), scoreSpan(s.score), esc(copy("farm_score_note"))) +
      tile(gl("OrgSur+", "sur_plus"), '<span class="' + tierInk(s.financial_score, "z") + '">' + esc(nInt(s.financial_score)) + "</span>", "descriptive index, 100 + 10z across 30 orgs, no eval artifact") +
      tile(gl("Farm surplus", "surplus_value"), esc(moneyMM(s.farm_surplus_mm)), "sum of expected values; " + esc(nInt(s.n_prospects)) + " prospects, mean age " + esc(n1(s.avg_age)), "", d.links.farm);
    var keys = [["acquisition_strategy", "ACQ"], ["development", "DEV"], ["financial", "FIN"], ["mlb_production", "PROD"]];
    var chips = '<div class="fr-chips">' + keys.map(function (k) {
      var br = s.branches[k[0]] || {};
      return '<a class="fr-lchip" href="' + esc(d.links.farm_tree) + '"><span class="fr-lchip-meta">' + esc(k[1]) + "</span><b>" + esc(br.letter || "-") + '</b><span class="fr-lchip-meta">#' + esc(br.rank) + " &middot; " + esc(n1(br.score)) + "</span></a>";
    }).join("") + "</div>";
    var hist = spark(s.history.map(function (r) { return [r[0], r[1]]; }), undefined, "farm score by snapshot");
    var mv = s.rank_movement || {};
    var extra = mini([
      ["Top prospect", s.top_prospect ? '<a href="/prospx/#player=' + esc(s.top_prospect.key) + '">' + esc(s.top_prospect.name) + "</a> FV " + esc(s.top_prospect.fv) : ""],
      ["ETA alignment (years)", esc(signed(s.eta_align_years, 2))],
      ["Rank movement", esc(mv.direction || "") + (isNum(mv.from_rank) ? " (#" + esc(mv.from_rank) + " to #" + esc(mv.to_rank) + ")" : "")],
      ["Health burden", esc(n1(s.health_burden))]
    ]);
    return '<div class="fr-tiles">' + t + "</div>" + '<p class="fr-count">' + esc(copy("letter_note")) + "</p>" + chips +
      "<h3>Farm score since the first snapshot</h3>" + hist + '<p class="fr-count">' + esc(s.history.length) + " snapshots</p>" + extra;
  }
  function secFin(d) {
    var s = d.sections.fin, sp = s.space_2027 || {}, ml = s.mlb_leg || {};
    var aav = s.tax_payroll_2027_source === "guaranteed_aav";
    var t = tile(gl("Cost+", "cost_plus"), '<span class="fr-neutral">' + esc(nInt(s.cost_plus)) + "</span>", esc(copy("fin_cost_plus_note")), "", d.links.ledger) +
      tile(gl("Space " + esc(DATA.class_year), "cbt_space"), signedMoney(sp.spotrac_usd), esc(copy("space_label_spotrac")) + "<br>" + esc(copy("space_label_platform")) + ": " + signedMoney(sp.platform_usd), "", d.links.ledger) +
      tile(gl("Tax payroll " + esc(DATA.class_year), "cbt_payroll"), esc(money(s.tax_payroll_2027)), "committed " + esc(money(s.committed_2027)) + " (Spotrac)" +
        (aav ? '<br><span class="fr-tag" title="' + esc(copy("tax_floor_note")) + '">' + esc(copy("cbt_basis_aav_label")) + "</span>" : ""), "", d.links.ledger) +
      tile(gl("Payor tier", "payor_tier"), esc((s.payor_2027 || {}).value || ""), esc((s.payor_2027 || {}).basis || ""), "", d.links.ledger) +
      tile("$ per projected win", esc(money(s.usd_per_win)), "the Cost+ denominator over projected wins less the locked free agents; plain dollars, no ladder", "", d.links.ledger) +
      tile("Recent spend, 3 winters", esc(money(s.recent_spend)), "largest guarantee " + esc(money(s.max_guar)) + " &middot; " + esc(nInt(s.n100m)) + " deals of 100M+", "", d.links.fa_archive);
    // Cost+ in its parts (owner answers M13-4 and COSTPLUS-1): the numerator and
    // the three denominator parts, each on its own row, never added together.
    var P = s.cost_plus_parts || {}, L = copy("cost_plus_part_labels") || {}, F = s.locked_fa_2027 || {};
    var parts = isNum(P.guaranteed_usd) ? mini([
      [esc(copy("cost_plus_numerator_label")), esc(n1(s.proj_war_2027)) + " less " + esc(n1(F.war)) + " (" + esc(nInt(F.n)) + " locked free agents) = " + esc(n1(s.proj_war_2027_ex_fa))],
      [esc(L.guaranteed || ""), esc(money(P.guaranteed_usd)) + (P.guaranteed_source === "guaranteed_aav" ? ' <span class="fr-tag">' + esc(copy("cbt_basis_aav_label")) + "</span>" : "")],
      [esc(L.arb || "") + " (" + esc(nInt(P.n_arb)) + ")", esc(money(P.arb_usd))],
      [esc(L.prearb || "") + " (" + esc(nInt(P.n_prearb)) + ")", esc(money(P.prearb_usd))]]) +
      '<p class="fr-count">' + prose(copy("cost_plus_parts_note")) + "</p>" : "";
    // The surplus figure is the MLB leg only (owner answer M13-2): no prospect
    // row is in it, so it never overlaps the FARM branch.
    var by = ml.by_salsrc_mm || {};
    var sur = mini([[gl(copy("mlb_leg_label"), "controlled_surplus"), '<span class="' + signCls(ml.mlb_mm) + '">' + esc(moneyMM(ml.mlb_mm)) + "</span>"]]
      .concat(Object.keys(by).map(function (k) { return ["&nbsp;&nbsp;" + esc(SALSRC_LABEL[k] || k.replace(/_/g, " ")), esc(moneyMM(by[k]))]; }))
      .concat([["Ladder sum " + esc(DATA.class_year) + " (arb and pre-arb rungs, as on /ledger/)", esc(money(d.sections.arbitration.proj_2027_usd))]]));
    return banner() + '<div class="fr-tiles">' + t + "</div>" + parts + sur +
      '<p class="fr-count">' + prose(copy("mlb_leg_note"), copy("surplus_ev"), copy("fin_no_ladder"), copy("fin_cost_plus_registry")) + "</p>";
  }
  // The MLB leg's salary-source split prints in words, not as payload keys.
  var SALSRC_LABEL = { arb_projection: "arbitration path", contract: "contracts" };
  function secMarket(d) {
    var s = d.sections.market;
    var fits = table(["Top fits", gl("fit", "team_fit"), "need", "afford", "window"], s.fits.map(function (r) {
      return [playerLink(r[0], r[1]) + ' <span class="fr-tag">' + esc(r[2]) + "</span>", n2(r[3]), n2(r[4]), n2(r[5]), n2(r[6])];
    }), 2);
    var out = table(["Outgoing", "prev AAV", "proj guar", "P10", "P90", "verdict"], s.outgoing.map(function (r) {
      return [playerLink(r[0], r[1]) + ' <span class="fr-tag">' + esc(r[2]) + "</span>", money(r[3]), money(r[4]), money(r[5]), money(r[6]), esc(r[7] || "")];
    }), 2);
    var W = 520, H = 72, n = s.winters.length, hi = 0;
    s.winters.forEach(function (w) { hi = Math.max(hi, Number(w[2]) || 0); });
    var bars = s.winters.map(function (w, i) {
      var bw = (W - 20) / Math.max(n, 1), h = hi ? (Number(w[2]) / hi) * (H - 22) : 0, x = 10 + i * bw;
      return '<rect class="fr-bar" x="' + (x + 3) + '" y="' + (H - 14 - h) + '" width="' + (bw - 6) + '" height="' + h + '"><title>' + esc(w[0] + ": " + w[1] + " signed, " + money(w[2])) + "</title></rect>" +
        '<text x="' + (x + bw / 2) + '" y="' + (H - 3) + '" text-anchor="middle">' + esc(String(w[0]).slice(2)) + "</text>";
    }).join("");
    var strip = '<div class="fr-strip"><svg viewBox="0 0 ' + W + " " + H + '" role="img" aria-label="guaranteed dollars signed by winter">' + bars + "</svg></div>";
    var rz = s.realized || {}, tot = rz.totals || {};
    var real = table(["Winter", "signed", "covered", "WAR to date", "paid", "surplus", "done"], (rz.by_winter || []).map(function (r) {
      return [esc(r[0]), nInt(r[1]), nInt(r[2]), n1(r[3]), money(r[4]), signedMoney(r[5]), nInt(r[6])];
    }), 2);
    return banner() + '<div class="fr-grid2"><div>' + fits + '<p class="fr-count">' + esc(copy("market_fits_note")) + "</p></div><div>" + out + "</div></div>" +
      "<h3>Guaranteed dollars signed, by winter</h3>" + strip +
      "<h3>" + gl(copy("market_realized_title"), "realized_contract_value") + "</h3>" +
      '<p class="fr-note">' + esc(copy("market_realized_sentence")) + "</p>" + real +
      '<p class="fr-count">' + esc(nInt(tot.n_covered)) + " of " + esc(nInt(tot.n)) + " signings covered &middot; WAR to date " + esc(n1(tot.war_td)) + " &middot; paid " + esc(money(tot.paid_td)) + " &middot; surplus " + signedMoney(tot.surplus_td) +
      " &middot; method " + esc(rz.method) + ". " + esc(copy("market_realized_coverage")) + "</p>";
  }
  var PANEL_NOTE = { promotionTiming: "promotion_timing_note" };
  function secFrontOffice(d) {
    var s = d.sections.front_office;
    var panels = s.panels.map(function (p) {
      var rows = p.rows.map(function (r) {
        var z = r[3], w = isNum(z) ? Math.min(50, Math.abs(Number(z)) / 3 * 50) : 0;
        var bar = '<div class="fr-zbar fr-zhide"><span class="' + (isNum(z) && Number(z) < 0 ? "fr-zneg" : "fr-zpos") + '" style="left:' + (isNum(z) && Number(z) < 0 ? (50 - w) : 50) + "%;width:" + w + '%"></span><i class="fr-zmid"></i></div>';
        var val = r[0].indexOf("Share") >= 0 || r[0].indexOf("share") >= 0 || r[0] === "promoRate" || r[0] === "draftHitRate" || r[0] === "hhi" || r[0] === "bonusHHI" ? pct(r[2], 1)
          : /^n[A-Z]/.test(r[0]) ? nInt(r[2]) : r[0] === "aggrYears" ? signed(r[2], 2) : n2(r[2]);
        // a row with no z prints its value in the z slot where the value column hides (narrow)
        var last = isNum(z) ? '<span class="fr-zval ' + signCls(z) + '">' + esc(signed(z, 2)) + "</span>"
          : '<span class="fr-zval"><span class="fr-zshow">' + esc(val) + "</span></span>";
        return '<div class="fr-zrow"><span>' + esc(r[1]) + '</span><span class="fr-zhide">' + esc(val) + "</span>" + bar + last + "</div>";
      }).join("");
      var tags = p.tags.map(function (t) { return '<span class="fr-tag">' + esc(t) + "</span>"; }).join("");
      var note = PANEL_NOTE[p.key] ? '<p class="fr-count">' + prose(copy(PANEL_NOTE[p.key])) + "</p>" : "";
      var rule = p.rule && p.rule.text ? '<details class="fr-how"><summary>' + esc(copy("promotion_timing_rule")) + '</summary><p class="fr-count">' + esc(p.rule.text) + "</p>" +
        '<p class="fr-count">' + (p.rule.sources || []).map(function (x) { return '<a href="' + esc(x.url) + '" rel="noopener">' + esc(x.label) + "</a>"; }).join(" &middot; ") + "</p></details>" : "";
      return "<h3>" + esc(p.label) + tags + (p.window ? ' <span class="fr-basis">' + esc(p.window) + "</span>" : "") + "</h3>" + rows + note + rule;
    }).join("");
    var sim = s.similar.length ? '<h3>Similar farms</h3><div class="fr-chips">' + s.similar.map(function (x) {
      return '<a class="fr-lchip" href="#view=club&team=' + esc(x[0]) + '" data-frlink="1"><b>' + esc(x[0]) + '</b><span class="fr-lchip-meta">' + esc(n2(x[1])) + "</span></a>";
    }).join("") + "</div>" : "";
    return '<p class="fr-count">' + prose(copy("front_office_note"), copy("zbar_note")) + "</p>" + panels + sim;
  }
  function secDugout(d) {
    var s = d.sections.dugout, st = s.style || {}, rz = s.realized || {};
    var t = tile(gl("Steal attempts " + esc(DATA.season_now), "steal_break_even"), esc(nInt(st.attempts)), "success " + esc(pct(st.success_rate, 1)), "", d.links.management_club) +
      tile("Target mix", esc(pct(st.share_2B, 0)) + " 2B", esc(pct(st.share_3B, 0)) + " 3B") +
      tile("Break-even faced", esc(pct(st.mean_breakeven_faced, 1)), "mean over the attempts");
    var sp = spark(s.attempts_by_season, undefined, "steal attempts by season");
    var fam = rz.live ? table(["Family", "n", gl("realized mWPA", "realized_mwpa")], rz.families.map(function (r) {
      return [esc(r[1]) + '<span class="fr-tag">' + esc(copy("dugout_realized_tag")) + "</span>", nInt(r[2]), '<span class="' + signCls(r[3]) + '">' + esc(signed(r[3], 2)) + "</span>"];
    }).concat([["Defensive subs" + '<span class="fr-tag">count only</span>', nInt(rz.defensive_sub_n), ""]])) : dark("Realized rows", (DATA.sections_status.dugout_families || {}).blocked_on || "");
    var zk = [["hook", "hook"], ["pen", "pen"], ["bench", "bench"], ["ibb", "IBB"], ["visit", "visits"]];
    var zc = rz.style_z ? '<div class="fr-chips">' + zk.map(function (k) {
      var z = rz.style_z[k[0]];
      return '<span class="fr-lchip"><span class="fr-lchip-meta">' + esc(k[1]) + " z</span><b>" + esc(signed(z, 1)) + "</b></span>";
    }).join("") + "</div>" : "";
    return '<div class="fr-tiles">' + t + "</div><h3>Attempts by season</h3>" + sp +
      '<p class="fr-note">' + esc(copy("dugout_sentence")) + "</p>" +
      "<h3>Realized value per family, " + esc(rz.season || "") + (rz.partial ? " (partial season)" : "") + "</h3>" + fam +
      '<p class="fr-count">' + esc(copy("dugout_not_summed")) + " &middot; agent: " + esc(rz.agent || "") + ". " + esc(copy("dugout_agent")) + "</p>" +
      zc + '<p class="fr-count">' + esc(copy("dugout_style")) + "</p>";
  }
  function secArbitration(d) {
    var s = d.sections.arbitration, b = branchOf(d, "arbitration");
    var flag1 = (s.flags || {})["1"] || 0;
    // The board tile prints the split the artifact supports (class 1-4 against
    // every row incl. pre-arb) and the cost tile says what its sum contains, so
    // the two agree with /arbitration/#teams one click away.
    var t = leafTile(leafBy(b, "n_arb"), "of " + esc(nInt(s.n_rows)) + " rows on the club board; " + esc(nInt(s.n_pre_arb)) + " pre-arb (class 0)") +
      tile(gl("Projected " + esc(DATA.class_year) + " cost", "arb_exposure"), esc(money(s.proj_2027_usd)), esc(copy("arb_cost_sum")) + " &middot; " + esc(copy("arb_tender_note")) + " &middot; " + esc(copy("arb_flag_note")) + ": " + esc(flag1), "", d.links.arbitration_teams) +
      tile(gl("Projected WAR of the class", "war"), esc(n1(s.proj_war_2027)), "fWAR basis, " + esc(DATA.class_year)) +
      tile("Realized " + esc(DATA.season_now) + " spend", esc(money((s.realized_2026 || {}).actual_usd)), esc(nInt((s.realized_2026 || {}).n)) + " settled rows", "", d.links.arbitration_history);
    var rows = table(["Player", "token", "proj", "lo", "hi", "WAR", "class"], s.rows.map(function (r) {
      return [esc(r[0]), esc(r[2] || ""), money(r[3]), money(r[4]), money(r[5]), n1(r[6]), nInt(r[7])];
    }), 2);
    var ou = '<div class="fr-tiles">' +
      tile("ou_mkt, all seasons", signedMoney(s.ou_mkt_total_usd), esc(copy("ou_mkt"))) +
      tile("ou_war, all seasons", signedMoney(s.ou_war_total_usd), esc(copy("ou_war"))) + "</div>" +
      '<p class="fr-note">' + esc(copy("never_combine")) + "</p>";
    return banner() + '<div class="fr-tiles">' + t + "</div>" + rows + '<p class="fr-count">' + esc(copy("arb_flag_key")) + "</p>" + ou;
  }
  function secPark(d) {
    var s = d.sections.park, f = s.factors, sw = s.short_window, v = s.venue || {};
    var src = f ? f : (sw || {});
    var t = tile(gl("Park factor, runs", "park_factor"), '<span class="fr-neutral">' + esc(src.runs == null ? "" : String(src.runs)) + "</span>", esc(copy("park_not_tiered")), "", d.links.parks) +
      tile("Park factor, wOBA", '<span class="fr-neutral">' + esc(src.woba == null ? "" : String(src.woba)) + "</span>", "100 = neutral") +
      tile("Park factor, HR", '<span class="fr-neutral">' + esc(src.hr == null ? "" : String(src.hr)) + "</span>", "100 = neutral") +
      tile("Venue", esc(v.name || ""), esc([v.city, v.state].filter(Boolean).join(", ")) + (isNum(v.capacity) ? " &middot; capacity " + esc(Number(v.capacity).toLocaleString("en-US")) : ""));
    var short = sw ? '<p class="fr-note">' + esc(sw.venue || "") + ": " + esc(sw.window || "") + ", " + esc(sw.year_range || "") + ", " + esc(Number(sw.n_pa || 0).toLocaleString("en-US")) + " PA. " + esc(copy("park_short_note")) + "</p>" : "";
    var dims = v.dims || {};
    var plate = mini([["Roof", esc(v.roof || "")], ["Surface", esc(v.turf || "")], ["Elevation (ft)", esc(nInt(v.elevation_ft))],
                      ["LF / CF / RF (ft)", esc([dims.leftLine, dims.center, dims.rightLine].map(function (x) { return x == null ? "-" : x; }).join(" / "))],
                      ["Azimuth", esc(n1(v.azimuth))]]);
    var hand = s.by_hand ? "<details><summary>By batter hand</summary>" + mini(Object.keys(s.by_hand).map(function (k) { return [esc(k), esc(JSON.stringify(s.by_hand[k]))]; })) + "</details>" : "";
    return '<div class="fr-tiles">' + t + "</div>" + short + plate + hand +
      '<p class="fr-count">' + esc(copy("park_source")) + "</p>" + dark("Attendance", (DATA.sections_status.park_attendance || {}).blocked_on || copy("park_attendance"));
  }
  function secHistory(d) {
    var s = d.sections.history;
    var W = 520, H = 72, n = s.standings.length;
    var bars = s.standings.map(function (r, i) {
      var g = (r[1] || 0) + (r[2] || 0), p = g ? r[1] / g : 0;
      var bw = (W - 10) / Math.max(n, 1), h = p * (H - 22), x = 5 + i * bw;
      return '<rect class="' + (p >= 0.5 ? "fr-bar" : "fr-bar-lo") + '" x="' + (x + 1) + '" y="' + (H - 14 - h) + '" width="' + (bw - 2) + '" height="' + h + '"><title>' + esc(r[0] + ": " + r[1] + "-" + r[2] + ", run differential " + signed(r[3], 0) + ", division rank " + r[4]) + "</title></rect>" +
        (i % 2 === 0 ? '<text x="' + (x + bw / 2) + '" y="' + (H - 3) + '" text-anchor="middle">' + esc(String(r[0]).slice(2)) + "</text>" : "");
    }).join("");
    var strip = '<div class="fr-strip"><svg viewBox="0 0 ' + W + " " + H + '" role="img" aria-label="wins and losses by season"><line class="fr-axis" x1="5" x2="' + (W - 5) + '" y1="' + (H - 14 - 0.5 * (H - 22)) + '" y2="' + (H - 14 - 0.5 * (H - 22)) + '"/>' + bars + "</svg></div>";
    var line = spark(s.bwar, 0, "club bWAR by season");
    var t = (s.best ? tile("Best season since " + esc(String(s.standings[0] ? s.standings[0][0] : "")), esc(s.best[0]), esc(s.best[1] + "-" + s.best[2]) + " &middot; run differential " + esc(signed(s.best[3], 0))) : "") +
      (s.worst ? tile("Worst season", esc(s.worst[0]), esc(s.worst[1] + "-" + s.worst[2]) + " &middot; run differential " + esc(signed(s.worst[3], 0))) : "");
    var spine = (s.spine || []).map(function (iv) { return esc(iv.team_id) + " " + esc(iv.first) + "-" + esc(iv.last); }).join(" &middot; ");
    return "<h3>Wins and losses, " + esc(s.standings.length ? s.standings[0][0] : "") + " to " + esc(s.standings.length ? s.standings[s.standings.length - 1][0] : "") + "</h3>" + strip +
      '<p class="fr-count">' + prose(copy("history_note"), copy("history_pennants")) + "</p>" +
      "<h3>Club bWAR by season</h3>" + line + '<p class="fr-count">' + esc(copy("bwar_basis")) + " &middot; spine: " + spine + " &middot; " + esc(s.bwar.length) + " seasons</p>" +
      '<div class="fr-tiles">' + t + "</div>" + hofTile(d, s.hof || {});
  }
  // THE HALL OF FAME TILE re-serves /hof/'s Franchises section: one franchise
  // per inductee under the owner's frozen rule (2026-09-25). Every figure and
  // sentence is a payload key; dark again with /hof/'s wording if that is dark.
  var IND_LABEL = { player_bbwaa: "Player, writers", route_unverified: "Inducted, route unverified" };
  function hofTile(d, h) {
    if (!h.live) return dark("Hall of Fame inductees", h.why || h.blocked_on || "");
    var sub = esc(nInt(h.n_player_bbwaa)) + " elected by the writers as players, " +
      esc(nInt(h.n_route_unverified)) + " by another route &middot; " +
      esc(nInt(h.n_played_for)) + " inductees played for the club";
    var rows = (h.inductees || []).map(function (r) {
      return [esc(r[0]), n1(r[1]), nInt(r[2]), n1(r[3]), esc((IND_LABEL[r[4]] || r[4] || "") + (r[5] ? " " + r[5] : ""))];
    });
    var list = rows.length
      ? "<details><summary>" + esc(nInt(rows.length)) + " inductees credited to the club</summary>" +
        table(["Inductee", "WAR with club", "Seasons", "Career WAR", "Induction"], rows, 3) + "</details>"
      : "";
    return "<h3>Hall of Fame</h3>" +
      '<div class="fr-tiles">' + tile("Hall of Fame inductees", esc(nInt(h.n)), sub, "", d.links.hof) + "</div>" + list +
      '<p class="fr-count">' + esc(h.rule || "") + " Frozen " + esc(h.rule_frozen || "") + ". " + esc(h.credit_basis || "") + "</p>";
  }
  // THE PENNANT TILE DURING THE POSTSEASON (docs/betting-2026-10/BRACKET_SIM_GATE.md
  // section 8): while the bracket simulator serves, the tile and its World Series
  // line read s.bracket, labelled implied, no market, with that row's own chip and
  // as-of date; the Playoffs tile, its division and bye lines and Projected wins
  // keep the season simulator, its stamp and the section chip. Without s.bracket
  // the tile renders exactly as before.
  function pennantTile(d, s) {
    var b = s.bracket;
    if (!b) return tile("Pennant", esc(pct(s.pennant_pct, 1)), "World Series " + esc(pct(s.ws_pct, 1)), "", d.links.betting_futures);
    var chip = '<span class="eephus-beta fr-verdict" title="' + esc(b.basis) + '">' + esc(b.registry_row) + " " + esc(b.verdict) + "</span>";
    return tile("Pennant (" + esc(b.label) + ")", esc(pct(b.pennant_pct, 1)),
      "World Series " + esc(pct(b.ws_pct, 1)) + " &middot; as of " + esc(b.as_of) + " " + chip, "", d.links.betting_futures);
  }
  // STRENGTH OF SCHEDULE is measured over the games still on the schedule, so
  // once none are left (the regular season is over) the overlay carries no sos
  // and no rank. The tile then prints the page's null glyph and drops the rank
  // fragment; the IL line stays (smoke audit SCL05).
  function sosTile(s) {
    var has = isNum(s.sos);
    var big = has ? esc(pct3(s.sos)) : '<span title="not measured">-</span>';
    var rank = has && isNum(s.sos_rank) ? "rank " + esc(nInt(s.sos_rank)) + " &middot; " : "";
    return tile("Strength of schedule", big, rank + "IL out 60+: " + esc(isNum(s.il_out_60) ? nInt(s.il_out_60) : "-"));
  }
  function secOdds(d) {
    var s = d.sections.odds;
    var t = tile("Projected wins " + esc(DATA.season_now), esc(n1(s.proj_wins)), "band " + esc(nInt(s.p10)) + " to " + esc(nInt(s.p90)) + " &middot; " + esc(s.record || ""), "", d.links.betting_futures) +
      tile("Playoffs", esc(pct(s.playoff_pct, 1)), "division " + esc(pct(s.division_pct, 1)) + " &middot; bye " + esc(pct(s.bye_pct, 1)), "", d.links.betting_futures) +
      pennantTile(d, s) +
      tile(gl("Pythag vs actual", "pythag_pct"), esc(pct3(s.pythag_pct)), "actual " + esc(pct3(s.actual_pct)) + " &middot; " + esc(copy("pythag_label"))) +
      sosTile(s);
    // The season-over line comes from the Futures payload as written, so the two
    // surfaces cannot disagree about when the odds stopped learning. While the
    // bracket simulator serves, the reworded stamp and its line come from that
    // payload instead, quoted through the export.
    var asOf = s.bracket ? copy("odds_division_as_of") : copy("odds_as_of");
    var brLine = s.bracket ? copy("odds_bracket_line") : copy("odds_bracket_not_updated");
    return (asOf ? '<p class="fr-note"><strong>' + esc(asOf) + "</strong></p>" : "") +
      (brLine ? '<p class="fr-note"><strong>' + esc(brLine) + "</strong></p>" : "") +
      '<div class="fr-tiles">' + t + "</div>" +
      '<p class="fr-note">' + esc(copy("odds_interval")) + "</p>" +
      '<p class="fr-count">' + esc(copy("odds_ledger")) + ". " + esc(copy("odds_no_market")) + "</p>" +
      '<p class="fr-count">' + esc(copy("odds_win_total_basis")) + "</p>";
  }
  var SECTION_RENDER = { roster: secRoster, season: secSeason, outlook: secOutlook, farm: secFarm, fin: secFin,
                         market: secMarket, front_office: secFrontOffice, dugout: secDugout, arbitration: secArbitration,
                         park: secPark, history: secHistory, odds: secOdds };

  function renderClub() {
    var d = clubOf(state.team);
    if (!d) return '<p class="fr-note">' + esc(copy("load_error")) + "</p>";
    if (!hasBody(d)) {
      return renderMast(d) + (SHARD_STATE[d.code] === "failed"
        ? pxState("failed", esc(copy("load_error")))
        : pxState("loading", esc("Loading " + (d.name || d.code) + ".")));
    }
    var blocks = DATA.branch_order.map(function (key) {
      var fn = SECTION_RENDER[key];
      return '<section class="fr-block" data-frsec="' + esc(key) + '">' + head(d, key) + (fn ? fn(d) : "") + "</section>";
    }).join("");
    return renderMast(d) + '<div class="fr-top">' + renderRoot(d) + '<div class="fr-canopy">' + (state.tree !== "hidden" ? renderCanopy(d) : "") + "</div></div>" +
      renderTree(d) + how([copy("weights_note"), copy("score_basis")]) + blocks + rail(d);
  }
  // THE LINK RAIL (QCLC17): one strip at the foot, grouped by the module that
  // owns each link and labelled from the same map the Open-in strips use; a
  // key the map does not name prints as itself with spaces for its joins.
  var LINK_LABEL = (function () {
    var m = { fantasy_dynasty: "Dynasty" };
    Object.keys(OPEN_LINKS).forEach(function (sec) {
      OPEN_LINKS[sec].forEach(function (p) { if (!m[p[1]]) m[p[1]] = p[0]; });
    });
    return m;
  })();
  var MODULE_NAME = { mlbstats: "MLB Stats", projections: "Projections", prospx: "PROSPX", ledger: "Club Ledger",
                      fa: "Free Agency", management: "Management", arbitration: "Arbitration", parks: "Parks",
                      hof: "Hall of Fame", betting: "Betting", trademachine: "Trade Machine", fantasy: "Fantasy" };
  function rail(d) {
    var groups = [], by = {};
    Object.keys(d.links).filter(function (k) { return d.links[k]; }).forEach(function (k) {
      var mod = (/^\/([a-z]+)\//.exec(d.links[k]) || [])[1] || "";
      if (!by[mod]) { by[mod] = []; groups.push(mod); }
      by[mod].push('<a href="' + esc(d.links[k]) + '">' + esc(LINK_LABEL[k] || k.replace(/_/g, " ")) + "</a>");
    });
    return '<nav class="fr-links" aria-label="Related modules">' + groups.map(function (mod) {
      return '<span class="fr-links-group"><span class="fr-links-mod">' + esc(MODULE_NAME[mod] || mod) + "</span>" + by[mod].join("") + "</span>";
    }).join("") + "</nav>";
  }
  // HOW THIS WORKS: the method sentences sit in one collapsed block under the
  // tree (club) or the table (board), each printed whole from the payload.
  function how(parts) {
    var body = parts.filter(function (s) { return s; }).map(function (s) { return '<p class="fr-count">' + prose(s) + "</p>"; }).join("");
    var B = DATA.basis || {};
    var src = Object.keys(B).filter(function (k) { return B[k]; }).map(function (k) { var v = String(B[k]); return esc(k.replace(/_/g, " ")) + " " + esc(/^\d{4}-\d\d-\d\dT/.test(v) ? v.slice(0, 10) : v); }).join(" &middot; ");
    return '<details class="fr-how"><summary>' + esc(copy("how_title") || "How this works") + "</summary>" + body +
      (src ? '<p class="fr-count">Sources: ' + src + "</p>" : "") + "</details>";
  }

  // ---- the board ----------------------------------------------------------------
  var BOARD_COLS = [
    ["code", "Club", 1, null], ["index_score", "Index", 1, "franchise_index"], ["roster_score", "ROSTER", 0, "franchise_branch_score"],
    ["outlook_score", "OUTLOOK", 0, "franchise_branch_score"], ["farm_score", "FARM", 0, "franchise_branch_score"],
    ["cost_plus", "FIN (Cost+)", 0, "cost_plus"], ["wins_2027", "Wins " , 1, null], ["war", "eWAR", 0, "ewar"],
    ["tax_payroll_2027", "CBT payroll ", 1, "cbt_payroll"], ["farm_rank", "Farm rank", 0, null], ["playoff_pct", "Playoff", 0, null]
  ];
  var TEXT_COLS = { code: 1 };
  function boardCell(r, key) {
    var v = r[key];
    if (key === "code") return '<a href="#view=club&team=' + esc(r.code) + '" data-frlink="1" title="' + esc(r.name || "") + '">' + esc(r.code) + "</a>";
    if (key === "index_score") return '<span class="fr-board-letter">' + esc(r.index_letter || "-") + "</span>" + scoreSpan(v) + ' <span class="fr-tag">#' + esc(r.index_rank) + "</span>";
    if (key === "roster_score" || key === "outlook_score" || key === "farm_score") return scoreSpan(v);
    if (key === "cost_plus") return '<span class="fr-neutral">' + esc(nInt(v)) + "</span>";
    if (key === "wins_2027") return esc(n1(v));
    if (key === "war") return esc(n1(v));
    if (key === "tax_payroll_2027") return esc(money(v)) + (r.tax_floor_below_2027 ? ' <span class="fr-tag" title="' + esc(copy("tax_floor_note")) + '">AAV</span>' : "");
    if (key === "farm_rank") return esc(nInt(v));
    if (key === "playoff_pct") return esc(pct(v, 0));
    return esc(v == null ? "" : v);
  }
  function sortedBoard() {
    var rows = DATA.board.slice(), k = state.sort.key, asc = state.sort.asc;
    rows.sort(function (a, b) {
      var x = a[k], y = b[k];
      if (TEXT_COLS[k]) { x = String(x || ""); y = String(y || ""); return asc ? x.localeCompare(y) : y.localeCompare(x); }
      var nx = isNum(x) ? Number(x) : (asc ? Infinity : -Infinity);
      var ny = isNum(y) ? Number(y) : (asc ? Infinity : -Infinity);
      return asc ? nx - ny : ny - nx;
    });
    return rows;
  }
  // A glossary term inside a sort button is a span the tooltip engine wires
  // (eephus-gl.js reads any [data-gl]), held out of the tab order so the
  // button is the head's one stop; an <a> inside a <button> is not valid.
  function glInert(label, id) {
    return '<span class="g-term" data-gl="' + esc(id) + '" tabindex="-1">' + esc(label) + "</span>";
  }
  function renderBoard() {
    // THE SORTABLE HEADS (QCLA12): a native <button> inside <th scope=col
    // aria-sort>, the /arbitration/ pattern, so the sort state is announced and
    // Enter and Space need no key shim. The Playoff head names its model (QCLC20).
    var head = BOARD_COLS.map(function (c) {
      var label = c[1] + (c[0] === "wins_2027" || c[0] === "tax_payroll_2027" ? DATA.class_year : "");
      var lab = c[3] ? glInert(label, c[3]) : esc(label);
      var on = state.sort.key === c[0];
      var arrow = '<span class="fr-sort-ind" aria-hidden="true">' + (on ? (state.sort.asc ? "&#9650;" : "&#9660;") : "") + "</span>";
      var tip = c[0] === "playoff_pct" ? copy("board_playoff_title") : "";
      return '<th scope="col" class="' + (c[2] ? "" : "fr-bcol-hide") + '" aria-sort="' + (on ? (state.sort.asc ? "ascending" : "descending") : "none") + '"' +
        (tip ? ' title="' + esc(tip) + '"' : "") + ' data-export-text="' + esc(label) + '"><button type="button" class="fr-sort" data-frsort="' + esc(c[0]) + '">' + lab + arrow + "</button></th>";
    }).join("");
    var body = sortedBoard().map(function (r) {
      return "<tr>" + BOARD_COLS.map(function (c) { return '<td class="' + (c[2] ? "" : "fr-bcol-hide") + '">' + boardCell(r, c[0]) + "</td>"; }).join("") + "</tr>";
    }).join("");
    return '<p class="fr-lede">' + esc(copy("board_lede")) + "</p>" +
      '<div class="fr-board"><table class="fr-table"><thead><tr>' + head + "</tr></thead><tbody>" + body + "</tbody></table></div>" +
      how([copy("board_foot"), copy("score_basis"), copy("board_playoff_title")]);
  }

  // ---- GFX: the shared eephus-gfx.js board renderer draws the header ---------------
  function gfxSpec(d) {
    var rows = d.tree.branches.map(function (b) {
      var W = DATA.weights;
      return { cells: [
        { t: b.label }, { t: b.kind === "graded" ? (b.letter || "-") : "" },
        { t: b.kind === "graded" ? n1(b.score) : (b.headline || ""), c: b.kind === "graded" ? "accent" : "muted" },
        { t: b.kind === "graded" ? "#" + b.rank : "" },
        { t: b.kind === "graded" ? weightPct(W[b.key]) + (b.provisional ? " " + copy("outlook_chip") : "") : "" }
      ] };
    });
    return {
      kind: "board", module: "Franchises", accentToken: "--accent-cyan",
      title: d.name + " " + copy("root_eyebrow"),
      subtitle: (d.index.letter || "-") + " #" + d.index.rank + " of " + DATA.league.n + " (" + n1(d.index.score) + ") " + copy("root_sentence"),
      url: "eephus.io/franchise/#team=" + d.code, filenameBase: "eephus-franchise-" + String(d.code).toLowerCase(),
      caption: copy("score_basis"),
      board: { columns: [{ label: "Branch", frac: 0.22 }, { label: "Grade", frac: 0.12 }, { label: "Score", frac: 0.30 },
                         { label: "Rank", frac: 0.14 }, { label: "Weight", frac: 0.22 }], rows: rows, counts: [12] }
    };
  }

  // ---- render and wire ---------------------------------------------------------------
  function syncTabs() {
    Array.prototype.forEach.call(document.querySelectorAll("[data-frsection]"), function (b) {
      var on = b.getAttribute("data-frsection") === state.view;
      if (b.classList) b.classList.toggle("active", on);
      b.setAttribute("aria-selected", on ? "true" : "false");
    });
  }
  function render() {
    var root = el("franchise-app-root");
    if (!root) return;
    if (!DATA) {
      root.innerHTML = LOAD_ERROR ? pxState("failed", esc(LOAD_ERROR)) : pxState("loading", esc("Loading Franchises."));
      return;
    }
    var m = el("franchise-masthead");
    if (m) m.textContent = copy("masthead");
    root.innerHTML = state.view === "board" ? renderBoard() : renderClub();
    syncTabs();
    wire();
    try { if (window.EEPHUS_GL && EEPHUS_GL.wire) EEPHUS_GL.wire(root); } catch (e) { /* glossary optional */ }
    if (state.sec) {
      try { var target = el("fr-sec-" + state.sec); if (target && target.scrollIntoView) target.scrollIntoView(); } catch (e) { /* optional */ }
    }
    // The club file is asked for last, once this render is wired, so its own
    // render (on arrival) never runs inside this one.
    if (state.view === "club" && clubOf(state.team) && !hasBody(clubOf(state.team))) loadShard(state.team);
  }
  function wire() {
    var sel = el("fr-club");
    if (sel && sel.addEventListener) sel.addEventListener("change", function () { state.team = this.value; state.sec = ""; if (SHARD_STATE[state.team] === "failed") delete SHARD_STATE[state.team]; writeHash(); render(); });
    Array.prototype.forEach.call(document.querySelectorAll("[data-frtree]"), function (b) {
      b.addEventListener("click", function () {
        var v = b.getAttribute("data-frtree");
        state.tree = v; state.treeSet = true; writeHash(); render();
        try { var nb = document.querySelector('button[data-frtree="' + v + '"]'); if (nb && nb.focus) nb.focus(); } catch (e) { /* optional */ }
      });
    });
    Array.prototype.forEach.call(document.querySelectorAll("button[data-frsort]"), function (btn) {
      btn.addEventListener("click", function () {
        var k = btn.getAttribute("data-frsort");
        if (state.sort.key === k) state.sort.asc = !state.sort.asc;
        else { state.sort.key = k; state.sort.asc = !!TEXT_COLS[k]; }
        render();
        // The re-render replaced the button: focus returns to the sorted head,
        // so the next Tab moves along the heads, not to the CSV button.
        try { var nb = document.querySelector('button[data-frsort="' + k + '"]'); if (nb && nb.focus) nb.focus(); } catch (e) { /* optional */ }
      });
    });
    Array.prototype.forEach.call(document.querySelectorAll("a[data-frlink]"), function (a) {
      a.addEventListener("click", function (e) {
        var href = a.getAttribute("href") || "";
        if (href.indexOf("#") !== 0) return;
        e.preventDefault();
        try { if (typeof history !== "undefined" && history.replaceState) history.replaceState(null, "", href); } catch (err) { /* optional */ }
        readHash();
        render();
        try { if (typeof window !== "undefined" && window.scrollTo) window.scrollTo(0, 0); } catch (err) { /* optional */ }
      });
    });
    var g = el("fr-gfx");
    if (g && g.addEventListener) g.addEventListener("click", function () {
      var d = clubOf(state.team);
      try { if (d && window.EEPHUS_GFX && window.EEPHUS_GFX.open) window.EEPHUS_GFX.open(gfxSpec(d)); } catch (e) { /* export optional */ }
    });
  }
  function boot() {
    Array.prototype.forEach.call(document.querySelectorAll("[data-frsection]"), function (b) {
      b.addEventListener("click", function () {
        state.view = this.getAttribute("data-frsection");
        state.sec = "";
        writeHash();
        render();
      });
    });
    try {
      if (typeof window !== "undefined" && window.addEventListener) {
        window.addEventListener("hashchange", function () { readHash(); render(); });
      }
    } catch (e) { /* optional */ }
    // The lamp loader goes up before the fetch: with DATA still null, render()
    // paints its loading kind and the board replaces it when the fetch settles.
    render();
    fetch(DATA_URL, { cache: "no-cache" })
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
      .then(function (d) {
        DATA = d;
        CLUBS = {};
        (d.clubs || []).forEach(function (c) { CLUBS[c.code] = c; });
        state.sort.key = (d.board_default_sort || ["index_score"])[0];
        state.sort.asc = (d.board_default_sort || [])[1] === "asc";
        if (!state.treeSet) state.tree = wide() ? "canopy" : "hidden";
        readHash();
        ensureTeam();
        render();
      })
      .catch(function () { LOAD_ERROR = "Franchises did not load. Retry."; render(); });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
