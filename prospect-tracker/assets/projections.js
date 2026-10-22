/* Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
 * Unauthorized copying of this file, via any medium is strictly prohibited
 * Proprietary and confidential
 * Written by Noah J. Dengler (@ARKNDJL), 2026 */

// =============================================================================
// eephus.io MLB Projections app (/projections/)
// =============================================================================
// The FA module's projection engine (proj_lgbm_v1) applied to the whole
// league, plus PROSPX prospects joining at their projected ETA. One sidecar
// (data/mlb_projections.json, proj_export.py); standalone by design - no
// PROSPX boot payload, no FA sidecars. Every row carries floor/mean/ceiling
// probability buckets; veteran surplus prices every club-controlled season.
(function () {
  "use strict";

  const EM_DASH = " - ";
  let DATA = null;

  // Mirror of PROSPX's formatMetric, character-identical to the copy in fa.js -
  // same precision rules, same null token, same -0 collapse. This surface had
  // its OWN pair of one-off formatters instead, which is how the three MLB
  // boards ended up with three number vocabularies that agreed by luck rather
  // than by contract. The local mirror (rather than a shared import) is the
  // established convention here: fa.js keeps one for the same reason, so no
  // module surface has to pull in the PROSPX script. test_number_format_parity
  // pins the two copies identical so they cannot drift again.
  function formatMetric(value, type = "int") {
    const n = Number(value);
    if (value == null || value === "" || !Number.isFinite(n)) return EM_DASH;
    const z = n === 0 ? 0 : n;                       // collapse -0 -> 0
    const sign = z > 0 ? "+" : (z < 0 ? "-" : "");   // zero is unsigned
    const abs = Math.abs(z);
    // A value that ROUNDS to zero at the printed precision is zero and prints
    // unsigned. toFixed keeps the sign of a tiny negative, so -0.01 at one
    // decimal printed "-0.0" (218 board cells on /projections/, 2026-10-02), and
    // the signed types put a "+" or "-" on a printed 0.00. Both helpers read
    // the ROUNDED figure, never z itself.
    const fixed = (x, d) => (Number(x.toFixed(d)) === 0 ? (0).toFixed(d) : x.toFixed(d));
    const signAt = d => (Number(abs.toFixed(d)) === 0 ? "" : sign);
    switch (type) {
      case "int":      return String(Math.round(z));
      case "war":      return fixed(z, 1);
      case "rate":     return signAt(2) + abs.toFixed(2);
      case "surplusM": return signAt(1) + "$" + abs.toFixed(1) + "M";
      case "moneyM":   return (z < 0 && signAt(1) ? "-" : "") + "$"
                            + (abs >= 100 ? abs.toFixed(0) : abs.toFixed(1)) + "M";
      case "pct":      return fixed(z, 1) + "%";
      default:         return String(z);
    }
  }

  const fmtWar = v => formatMetric(v, "war");
  // Signature kept at one argument: every call site here passes dollars and
  // wants the millions form. The old body emitted "-$1.6M" for negatives,
  // which `moneyM` now does too (it used to drop the sign).
  const money = usd => (usd == null ? EM_DASH : formatMetric(usd / 1e6, "moneyM"));
  function esc(s) {
    return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }
  // The club's Franchises href through the hub's one club resolver
  // (EEPHUS_HUB.clubHref): "" for a code that is not one of the 30 clubs. The
  // literal shape is the fallback only where the hub is absent.
  function franchiseHref(code) {
    const H = typeof window !== "undefined" ? window.EEPHUS_HUB : null;
    if (H && H.clubHref) return H.clubHref(code);
    return code ? `/franchise/#team=${encodeURIComponent(code)}` : "";
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

  // ORG abbreviation -> ESPN logo slug (same map as build_site/prospx).
  const ESPN_SLUGS = {
    ARI: "ari", ATH: "ath", ATL: "atl", BAL: "bal", BOS: "bos",
    CHC: "chc", CHW: "chw", CIN: "cin", CLE: "cle", COL: "col",
    DET: "det", HOU: "hou", KCR: "kc", LAA: "laa", LAD: "lad",
    MIA: "mia", MIL: "mil", MIN: "min", NYM: "nym", NYY: "nyy",
    PHI: "phi", PIT: "pit", SDP: "sd", SEA: "sea", SFG: "sf",
    STL: "stl", TBR: "tb", TEX: "tex", TOR: "tor", WSN: "wsh",
  };
  // QMLP07: every mark here draws at 13 to 16 px, so it is asked for at 32 px
  // through ESPN's combiner (the shared EEPHUS_HUB size rule, as /fa/ does)
  // rather than as the 500 x 500 master: 28 board logos were 1.07 MB.
  const LOGO_PX = 32;
  function teamLogoSrc(org) {
    const H = window.EEPHUS_HUB;
    const viaHub = H && H.teamLogoURL ? H.teamLogoURL(org, LOGO_PX) : "";
    const slug = ESPN_SLUGS[org] || String(org).toLowerCase();
    return viaHub || `https://a.espncdn.com/combiner/i?img=/i/teamlogos/mlb/500/${slug}.png&h=${LOGO_PX}&w=${LOGO_PX}`;
  }
  function teamLogo(org) {
    if (!org) return "";
    return `<img class="fa-logo" src="${esc(teamLogoSrc(org))}" alt="${esc(org)}" loading="lazy" onerror="this.replaceWith('${esc(org)}')">`;
  }
  // A club mention links to its club (owner ask 9) through the hub's one club
  // resolver (EEPHUS_HUB.club + clubHref), never a raw payload code: a
  // prospect's club opens its farm system page (opts.ctx "farm"), every other
  // club its Franchises page. `inner` is the markup printed before (the mark,
  // the code). opts.mark makes a mark that sits beside its own linked code a
  // mouse twin (out of the tab order, hidden from a screen reader). A code the
  // hub does not know keeps its markup in a span marked
  // data-club-nolink="unresolved", never a guessed link.
  function clubA(org, inner, opts) {
    const o = opts || {};
    const H = typeof window !== "undefined" ? window.EEPHUS_HUB : null;
    if (!H || !H.club || !H.clubHref) return inner;
    const c = org ? H.club(org) : null;
    if (!c) return org ? `<span data-club-nolink="unresolved">${inner}</span>` : inner;
    const farm = o.ctx === "farm";
    return `<a class="club-link${o.cls ? " " + o.cls : ""}${o.mark ? " club-link--mark" : ""}" href="${esc(H.clubHref(c.code, farm ? "farm" : "franchise"))}"`
      + ` data-club="${c.code}" title="${esc(c.name + (farm ? ": farm system" : ": franchise overview"))}"`
      + (o.mark ? ` tabindex="-1" aria-hidden="true"` : "") + `>${inner}</a>`;
  }
  // The farm system href, through the same resolver ("" off the 30 clubs).
  function farmHref(code) {
    const H = typeof window !== "undefined" ? window.EEPHUS_HUB : null;
    if (H && H.clubHref) return H.clubHref(code, "farm");
    return code ? `/prospx/#farm-org=${encodeURIComponent(code)}` : "";
  }

  // ===========================================================================
  // Headshots (2026-08-04; face-cropped 2026-08-05). ONE builder for every
  // headshot this surface renders - the 24px board-row wells (ported from the
  // FA board, which reuses .fa-row-photo / .fa-row-headshot for the well and
  // the image), the 96px .mlbp-headshot on the player page, and the 132px hero
  // the shared GFX card draws. All three boxes are SQUARE.
  //
  // THE URL IS NOT THE FA ONE. fa.js requests the `d_people:generic` overlay
  // set, which Cloudinary answers with a SILHOUETTE at HTTP 200 whenever the
  // player has no photo in that context - fine for a board that is all MLB
  // veterans, fatal here, because a 200 never fires onerror and the milb-only
  // ids that most prospects have would be pinned to a grey outline forever.
  // So this reads data/photo_ctx.json (the resolver's id -> '67' | 'milb' |
  // 'none' map) and requests the context that actually HAS a photo, with no
  // overlay, exactly as PROSPX's headshotURL does. Coverage measured on the
  // current payload: 973 of 1324 veterans resolve directly, and all 209
  // prospects resolve through the player-links map below (59 '67', 146 'milb',
  // 4 'none').
  //
  // FACE CROP (2026-08-05). img.mlbstatic.com is Cloudinary and honours
  // `c_fill,g_face`: c_fill returns EXACTLY the requested box, g_face centres
  // that crop on the detected face. Source headshots are 480x720 (2:3), so the
  // square DOM boxes were papering over the mismatch with object-fit:cover
  // (which lops the top of the head off), and the card hero could not paper
  // over it at all - canvas drawImage has no object-fit, so it VERTICALLY
  // SQUASHED the face (see the CONTRACT note in eephus-hub.js). Asking for the
  // real box fixes all three and needs no consumer change. Verified live on
  // BOTH contexts: exact pixel dimensions back, Access-Control-Allow-Origin:*
  // intact, so the crops stay export-safe on the card canvas. Same transform
  // string as PROSPX's _GFX_FACE_CROP; c_thumb was rejected there for zooming
  // too tight on the face and is not reconsidered here.
  const FACE_CROP = "c_fill,g_face";
  let PHOTO_CTX = null;                 // null = not loaded yet, {} = failed

  // Square box in CSS px -> requested pixels. 2x for retina and for the 2x
  // supersample the card canvas exports at, with a 60px floor so a 24px well
  // still asks for something legible. Square in, square out - the aspect can
  // never drift, which is the whole point of the crop.
  function faceBox(px) { return Math.max(60, Math.round((px || 24) * 2)); }
  function cropURL(mlbam, seg, box) {
    return `https://img.mlbstatic.com/mlb-photos/image/upload/${FACE_CROP},w_${box},h_${box},q_auto:best/v1/people/${mlbam}/headshot/${seg}/current`;
  }

  function headshotURL(mlbam, px) {
    if (!mlbam) return null;
    const ctx = PHOTO_CTX ? PHOTO_CTX[String(mlbam)] : undefined;
    if (ctx === "none") return null;    // resolver checked: no photo on file
    if (ctx === "67" || ctx === "milb") return cropURL(mlbam, ctx, faceBox(px));
    // Unresolved: an id added since the last monthly backfill, or the map
    // failed to load. Ask for the real 67 photo with NO overlay so a miss 404s
    // and the one-shot MiLB retry below can recover it, instead of silently
    // returning a silhouette that nothing can detect.
    return cropURL(mlbam, "67", faceBox(px));
  }

  function rowPhotoImg(mlbam) {
    // Digits only. The id is interpolated into an inline onerror string below
    // and it arrives from a data payload, not from this file.
    const id = String(mlbam == null ? "" : mlbam).replace(/\D/g, "");
    if (!id) return "";
    const url = headshotURL(id, 24);
    if (!url) return "";
    const ctx = PHOTO_CTX ? PHOTO_CTX[id] : undefined;
    const resolved = (ctx === "67" || ctx === "milb");
    // The retry is the SAME square crop, only forced onto the MiLB set.
    const milb = cropURL(id, "milb", faceBox(24));
    // A resolved context is already the right set, so its onerror just drops
    // the image and leaves the empty well - never a broken-image glyph.
    const onerr = resolved
      ? "this.remove()"
      : `if(this.dataset.mt){this.remove()}else{this.dataset.mt=1;this.src='${milb}'}`;
    return `<img class="fa-row-headshot" src="${url}" alt="" loading="lazy" decoding="async" onerror="${onerr}">`;
  }

  // The well is ALWAYS emitted, photo or not: it is a fixed 24px grid column
  // in .proj-id, so nothing below it moves when an async fill lands.
  function rowPhoto(m) {
    if (m.mlbam) return `<span class="fa-row-photo">${rowPhotoImg(m.mlbam)}</span>`;
    return `<span class="fa-row-photo" data-photo-key="${esc(m.key || "")}"></span>`;
  }

  // Second pass for rows the payload carries no mlbam on. Veteran rows all
  // have one and render synchronously above; prospect rows are being given one
  // in proj_export, and until that lands (and for any row it misses) the
  // cross-module links map resolves the key. One pass per render.
  function fillRowPhotos(scope) {
    const pend = (scope || document).querySelectorAll(".fa-row-photo[data-photo-key]");
    if (!pend.length || !window.EEPHUS_HUB) return;
    window.EEPHUS_HUB.links().then(L => {
      if (!L) return;
      pend.forEach(el => {
        const row = (L.byKey || {})[el.dataset.photoKey];
        if (row && row.mlbam) el.innerHTML = rowPhotoImg(row.mlbam);
        el.removeAttribute("data-photo-key");
      });
    });
  }

  function posGroup(pos) {
    const head = String(pos || "").toUpperCase().split("/")[0].trim();
    if (["SP", "SP2", "P", "LHP", "RHP"].includes(head)) return "SP";
    if (["RP", "CL", "SIRP", "MIRP"].includes(head)) return "RP";
    if (head === "C") return "C";
    if (["1B", "2B", "3B", "SS", "IF"].includes(head)) return "IF";
    if (["LF", "CF", "RF", "OF"].includes(head)) return "OF";
    if (head === "DH" || head === "H") return "DH";
    return "IF";
  }

  // WAR heat is the value ruler's `war` family now (6 / 4 / 3 / 2.5 / 1.5 plus a
  // red step under zero), and the cuts live in assets/eephus-tiers.js. The old
  // local warClass banded 4 / 2.5 / 1, which put 60.2% of the 500 cells the
  // default board paints in ONE colour; the ruler's widest tier there is 38.6%,
  // and the #src=prospect view goes from one populated tier to four.

  // Projected RATE lines (vets only - fa_projection.rate_path arrays; the
  // prospect outcome model is FV-anchored and carries no rate machinery,
  // so prospect cells render a dash under a rate metric).
  // No cuts here. `state.cells` IS the ruler family name ("wrc" / "woba" /
  // "fip"), so a projected rate cell and the published /mlbstats/ column land on
  // the same ladder and a wRC+ of 121 cannot read two different tiers.
  const RATE_META = {
    wrc:  { label: "wRC+", fmt: v => String(Math.round(v)),
            tip: "projected wRC+ (park-neutral, 100 = league average)" },
    woba: { label: "wOBA", fmt: v => v.toFixed(3).replace(/^0(?=\.)/, ""),
            tip: "projected wOBA (Marcel components aged along the engine's curves)" },
    fip:  { label: "FIP", fmt: v => v.toFixed(2),
            tip: "projected FIP (lower is better)" },
    // PA/IP (PJ_7, dark): the year-1 playing time of the component lines,
    // offered only while the board payload carries components_live. It has no
    // ruler family, so its cells carry no tier colour and the board no key.
    pa:   { label: "PA/IP", fmt: v => String(Math.round(v)), noLadder: true,
            tip: "projected playing time, the component lines' year-1 PA or IP (FanGraphs frame)" },
  };
  // The PA/IP cell exists only when the board says the component lines are
  // live AND some row carries a year-1 pa or ip: proj_export adds the scalar
  // only where the PJ-C exposure test passed (PJ_8). A #cells=pa link on a
  // board without one falls back to WAR.
  const compLive = () => !!(DATA && DATA.components_live);
  let _ptFor = null, _ptOn = false;
  const ptLive = () => {
    if (!compLive()) return false;
    if (_ptFor !== DATA) {
      _ptFor = DATA;
      _ptOn = (DATA.vets || []).some(m => m.pa != null || m.ip != null);
    }
    return _ptOn;
  };
  function rateAt(m, t) {
    if (state.cells === "pa") return t === 0 ? (m.pa ?? m.ip ?? null) : null;
    const arr = state.cells === "wrc" ? m.wrc
      : state.cells === "woba" ? m.woba
      : state.cells === "fip" ? m.fip : null;
    return arr ? (arr[t] ?? null) : null;
  }
  function rateClass(v) {
    const mm = RATE_META[state.cells];
    return mm && !mm.noLadder ? EephusTiers.cls(v, state.cells) : "";
  }

  const state = { src: "all", pos: "all", team: "all", contract: "all", age: "all", q: "", sort: "warTotal",
                  dir: -1, limit: 100, player: null, view: "players", cmp: [],
                  // Season-cell metric: war (default) | wrc | woba | fip - the board's
                  // per-season cells re-render on the projected RATE line when toggled.
                  cells: "war",
                  // Talent-map scatter axes (user-pickable).
                  sx: "age", sy: "warY1",
                  // Team Outlook column sort: teamSort = column key (null keeps
                  // the export's roster-WAR order); teamDir = 1 natural / -1 reversed.
                  teamSort: null, teamDir: 1,
                  // Team Outlook slate: "proj" = the 2027 projection (default),
                  // "now" = the dark-launched Current (2026) view (#now=1 soak).
                  teamMode: "proj", teamModeTouched: false,
                  // Team Outlook drill-down (T7): the club whose player breakdown
                  // is open (#view=teams&club=XXX), or null.
                  club: null,
                  // Player-page tab (#ptab=, the key PROSPX uses). Held here so an
                  // async fill or a re-render never snaps the reader back to the
                  // first tab; PTAB_FOR scopes it to the player it was chosen on.
                  ptab: null };
  // The ids a #ptab= may name. Anything else in a share link falls back to the
  // first tab instead of leaving no panel visible.
  const PTABS = ["overview", "hitting", "pitching", "defense", "value", "projection", "scouting", "discussion"];
  let PTAB_FOR = null;
  // Player cards: {players: {key: card}}, filled one shard at a time from
  // data/mlb_player_detail/<key>.json (QMLP01). The 4.8 MB whole set is read
  // only when a shard is missing (a deploy that predates the shards).
  let DETAIL = null;
  const CARD_LOADING = Object.create(null);
  let DETAIL_ALL_LOADING = false;
  let PAINTED_PLAYER = null;    // the card on screen, so a late board does not repaint it
  let FIELDING = null;          // games by position, nightly, keyed by MLBAM id; lazy
  let FIELDING_LOADING = false;
  let PITCHLB = null;           // {byMlbam:{...}} from the /mlbstats/ leaderboards, lazy
  let PITCHLB_LOADING = false;
  let SWINGD = null;            // data/swing_delta.json (bat-tracking year-over-year), lazy
  let SWINGD_LOADING = false;
  let SCC = null;               // Statcast catcher runs by MLBAM (statcast_catcher_export.py), lazy
  let SCC_LOADING = false;

  // Board sort keys. Every key a share link has ever carried keeps working (the
  // retired tape bar's y0..y4 / warPeak / thru, the card header's rank / name /
  // warTotal / aav / age / sur) plus the prospect columns. Anything else falls
  // back to the default instead of sorting every row as a tie.
  // `thru` was the contract column's key until 2026-09-17; syncFromURL aliases
  // it to `ctrl`, so a saved share link resolves to the Control column that
  // replaced it instead of silently falling back to the default order.
  const SORT_KEYS = ["warTotal", "rank", "name", "team", "sur", "y0", "y1", "y2", "y3", "y4",
                     "age", "aav", "ctrl", "warPeak", "warPrime", "fv", "eta", "pBust"];
  // First click ascending: A-Z, youngest, soonest, safest.
  const ASC_FIRST = ["name", "team", "age", "eta", "pBust"];
  function naturalDir(k) { return ASC_FIRST.includes(k) ? 1 : -1; }
  // The prospect column set replaces the contract tail. Both filters that
  // leave only prospects switch to it.
  function prospectView() { return state.src === "prospect" || state.contract === "prospect"; }
  // Keys with a header (or a picker entry) in a column set. One list, read by
  // the header, the sort picker and the orphaned-sort reset in render().
  function viewSortKeys(pros) {
    return ["rank", "name", "team", "warTotal", "sur", "y0", "y1", "y2", "y3", "y4", "age"]
      .concat(pros ? ["fv", "eta", "warPeak", "warPrime", "pBust"] : ["aav", "ctrl"]);
  }

  function syncFromURL() {
    const p = new URLSearchParams(location.hash.slice(1));
    state.player = p.get("player") || null;
    state.ptab = PTABS.includes(p.get("ptab")) ? p.get("ptab") : null;
    PTAB_FOR = state.player;
    state.view = ["teams", "accountability"].includes(p.get("view")) ? p.get("view") : "players";
    state.club = p.get("club") || null;
    state.cmp = (p.get("cmp") || "").split(",").filter(Boolean).slice(0, 2);
    if (p.has("src")) state.src = p.get("src");
    if (p.has("pos")) state.pos = p.get("pos");
    if (p.has("team")) state.team = p.get("team");
    // `controlled` was one bucket until 2026-09-17, when the payload learned to
    // tell a club-controlled player from a man with no deal on file at all. A
    // saved link carrying it lands on the half that kept its meaning.
    if (p.has("contract")) state.contract = p.get("contract") === "controlled" ? "ctrl" : p.get("contract");
    if (p.has("age")) state.age = p.get("age");
    // Whitelist like view above: an arbitrary #cells= value (typo, truncated
    // share link) would crash renderTable's header template on
    // RATE_META[state.cells].label - fall back to the WAR default instead.
    if (p.has("cells") && ["war", "wrc", "woba", "fip", "pa"].includes(p.get("cells"))) state.cells = p.get("cells");
    if (p.has("sx")) state.sx = p.get("sx");
    if (p.has("sy")) state.sy = p.get("sy");
    if (p.has("q")) state.q = p.get("q");
    if (p.has("sort")) {
      const _s = p.get("sort") === "thru" ? "ctrl" : p.get("sort");
      state.sort = SORT_KEYS.includes(_s) ? _s : "warTotal";
    }
    state.dir = p.get("dir") === "asc" ? 1 : p.get("dir") === "desc" ? -1 : naturalDir(state.sort);
  }
  function syncToURL() {
    const p = new URLSearchParams();
    if (state.player) p.set("player", state.player);
    if (state.player && state.ptab && PTAB_FOR === state.player) p.set("ptab", state.ptab);
    if (state.view !== "players") p.set("view", state.view);
    if (state.view === "teams" && state.club) p.set("club", state.club);
    if (state.cmp.length) p.set("cmp", state.cmp.join(","));
    if (state.src !== "all") p.set("src", state.src);
    if (state.pos !== "all") p.set("pos", state.pos);
    if (state.team !== "all") p.set("team", state.team);
    if (state.contract !== "all") p.set("contract", state.contract);
    if (state.age !== "all") p.set("age", state.age);
    if (state.cells !== "war") p.set("cells", state.cells);
    if (state.sx !== "age") p.set("sx", state.sx);
    if (state.sy !== "warY1") p.set("sy", state.sy);
    if (state.q) p.set("q", state.q);
    if (state.sort !== "warTotal") p.set("sort", state.sort);
    if (state.dir !== naturalDir(state.sort)) p.set("dir", state.dir > 0 ? "asc" : "desc");
    const h = p.toString();
    history.replaceState(null, "", h ? `#${h}` : location.pathname);
  }

  // Season-aligned WAR for a row: vets start at first_season; prospects at
  // their ETA (pre-ETA seasons are MiLB time - rendered as such, never 0).
  // THE BOARD SHOWS THE EXPECTED VALUE (owner decision 2026-09-18). It used to
  // show the "playing-time-held" (if-healthy) 70th-percentile path, asked for
  // on 2026-06-13 after the Skenes year-5 report so a star's out-years read at
  // their healthy level. That path answers "how good is he when he plays",
  // which is the wrong question for a board whose next column is surplus: it
  // strips out exactly the attrition a club is buying, and it strips most from
  // the players who carry most of it. Measured on the served board the day it
  // was reverted, the if-healthy total ran 37.9 percent above the expected
  // value league-wide and the median row nearly halved (ratio 0.563), while a
  // two-way pitcher's arm, the case that raised it, moved only 12 percent.
  // Surplus and all valuation ALREADY priced the expected value (m.war /
  // surNpv) and do not move; this aligns the display with what was always
  // being priced. warPTH stays on the payload and on the player card.
  // The player's full remaining surplus, in raw dollars. `surTotal`
  // (2026-08-03) is the balance of the season in progress plus the NPV of every
  // controlled season after it; `surNpv` counted only seasons from
  // DATA.first_season on, so a contract ending this year showed no surplus at
  // all even while its club still controlled the player for months.
  //
  // The trade board prices surTotal, and the two surfaces are required to agree
  // per player (test_calibration_vintage: "the same player is worth the same on
  // every surface"), so this page reads the same field. Prospect rows are
  // unaffected: they carry surNpv only.
  function surOf(m) {
    if (!m) return null;
    if (m.surTotal != null) return m.surTotal;
    return m.surNpv != null ? m.surNpv : null;
  }
  // THE PRICED HORIZON (M05-01, 2026-09-25). Surplus priced the five projected
  // seasons and nothing after them until the contract tail (pricedTail below)
  // priced the 39 guarantees that run past them. A row still clamped (ctrlWhy
  // "horizon": the flag off, or a guarantee longer than the champion path) keeps
  // this treatment: the number is a statement about those seasons, not about the
  // club control window, so every surface that labels it names the seasons it
  // covers and states the guaranteed seasons after them as unpriced. The seasons
  // are read off the row's own salary path, never assumed.
  function horizonTail(m) {
    if (!m || m.ctrlWhy !== "horizon") return null;
    const ct = ctrlThruOf(m);
    let first = null, end = null;
    (m.salPath || []).forEach(st => {
      const s = Number(st[0]);
      if (first == null || s < first) first = s;
      if (end == null || s > end) end = s;
    });
    if (end == null || ct == null || ct <= end) return null;
    const n = ct - end;
    return { first, end, n, from: end + 1, to: ct,
      committed: m.aav ? m.aav * n : null };
  }
  function horizonTailText(m, tl) {
    const span = tl.n === 1 ? `guaranteed ${tl.from} season` : `${tl.n} guaranteed seasons ${tl.from}-${tl.to}`;
    return `The ${span}${tl.committed != null ? ` (about ${money(tl.committed)} at ${money(m.aav)}/yr)` : ""} carr${tl.n === 1 ? "ies" : "y"} no price.`;
  }
  // THE CONTRACT TAIL (owner answer 2026-09-25, M05-01 step 2). A guarantee
  // that runs past the five projected seasons is now priced through its last
  // season (proj_export.PRICE_CONTRACT_TAIL), and the seasons past the five
  // price on the champion (Marcel) aging curve CHAINED FROM THE LAST PRINTED
  // SEASON's WAR (owner answer VAL2-Q1, proj_export.TAIL_SEAM; the FA module's
  // own seam), which the board does not print; `warTail` carries the WAR each
  // one priced. The surplus is labelled with the whole span it covers, read off
  // the row's own salary path.
  function pricedTail(m) {
    if (!m || !DATA || DATA.first_season == null) return null;
    const lastH = DATA.first_season + DATA.horizon - 1;
    let first = null, end = null, n = 0;
    (m.salPath || []).forEach(st => {
      const s = Number(st[0]);
      if (first == null || s < first) first = s;
      if (end == null || s > end) end = s;
      if (s > lastH) n++;
    });
    if (!n) return null;
    return { first, end, n, from: lastH + 1 };
  }
  // Their P10/P90 (warP10Tail / warP90Tail, owner answers VAL2-Q3 and
  // VAL2-Q3-REVIEW (b)) are the last printed season's P10/P90 chained the same
  // way, the P10 never floored at zero, and the trade value's range spans them.
  function pricedTailText(tp) {
    const span = tp.n === 1 ? `guaranteed ${tp.from} season prices` : `${tp.n} guaranteed seasons ${tp.from}-${tp.end} price`;
    return `The ${span} on the champion (Marcel) aging curve chained from the ${tp.from - 1} WAR, past the five seasons the board prints. `
      + `Their P10 and P90 are the ${tp.from - 1} P10 and P90 chained the same way, the P10 not floored at zero, and the trade value's P10-P90 range runs through ${tp.end}.`;
  }
  function warAt(m, t) {
    const arr = m.war;
    if (m.src === "prospect") {
      const off = t - (m.eta - DATA.first_season);
      return off >= 0 && off < (arr || []).length ? arr[off] : null;
    }
    return (arr || [])[t] ?? null;
  }
  function bandAt(m, t, which) {
    // The P10/P90 bands of the EXPECTED path, for every row. They were
    // described here as "the prime-path bands" while the board still printed
    // the prime path; warP10/warP90 have always been the expected-path bucket
    // paths (proj_export writes the prime ones to warPTHP10/warPTHP90), so the
    // comment named the wrong series and the cell it wrapped never moved.
    const arr = which === "lo" ? m.warP10 : m.warP90;
    if (!arr) return null;
    if (m.src === "prospect") {
      const off = t - (m.eta - DATA.first_season);
      return off >= 0 && off < arr.length ? arr[off] : null;
    }
    return arr[t] ?? null;
  }

  // The DISPLAYED 5-year (windowed, ETA-aligned) WAR total, so the board sorts on
  // the same number the Total column shows. Prospects get the in-window sum only
  // (a late-ETA prospect's off-window prime years do NOT float him up the board);
  // vets keep their full expected-value total (already 5-year, truncated at export).
  // WHICH RULER A ROW IS PAINTED ON. A prospect expected path is bucket-weighted
  // by P(bucket|FV), so the whole prospect pool sits under the war ladder's
  // bottom cut and would be one colour. `warProspect` bands the prospect pool to
  // the SHAPE the war ladder has on its own pool, so the same colour means the
  // same rank in the population the row belongs to. The cuts are fitted, and
  // refitted on 2026-09-18b because the first fit was pinned to the if-healthy
  // display that the revert had already replaced; eephus-tiers.js carries the
  // measurement and test_value_ruler re-measures it on the served board.
  // This function answers for the SEASON cells and the 5y total alike -- the
  // total cell was left on "war" when warProspect shipped and painted 182 of
  // 183 prospect rows one colour.
  function warLadder(m) { return m.src === "prospect" ? "warProspect" : "war"; }
  function warShown(m) {
    if (m.src === "prospect") {
      let s = null;
      for (let t = 0; t < DATA.horizon; t++) {
        const w = warAt(m, t);
        if (w != null) s = (s == null ? 0 : s) + w;
      }
      return s;
    }
    return m.warTotal;
  }
  // How many season cells this row actually PAINTS. The 5y total bands on the
  // average of THOSE seasons, not on total / horizon: warShown gives a prospect
  // the in-window sum only, and 69 of 183 prospects have fewer than five
  // in-window seasons, so dividing by five banded a late-ETA prospect a tier low
  // (worst measured case 3.6 WAR over 2 seasons: 0.72/yr against 1.81/yr). For a
  // vet this is 5 and nothing moves.
  function nPainted(m) {
    let n = 0;
    for (let t = 0; t < DATA.horizon; t++) if (warAt(m, t) != null) n++;
    return n;
  }

  // THE PROSPECT TALENT PATH, the second series a prospect row publishes.
  // value_framework.prospect_prime_path is P(bucket|FV)-weighted exactly as the
  // expected path is -- it carries the same bust probability -- and differs in
  // one thing only: the bucket levels reconcile to the PRIME anchor instead of
  // the realized 6-year-average anchor. It is a TALENT level, not a forecast of
  // what a club collects, so it never enters the sort of the board, the colour
  // of the WAR cells or any priced number; it is published beside the expected
  // value, under its own name, so the reader sees the gap instead of being
  // handed one of the two without being told which.
  //
  // WHY NOT IN THE 5y COLUMN. Measured 2026-09-18 on the served artifact: on the
  // expected path Jesus Made (eFV 62) is 113th of the 1,566 rows on this board.
  // Print his prime total in the same column and he is 17th, ahead of Elly De La
  // Cruz and Jackson Chourio, and 9 prospects enter the top 50 where none are
  // now. That board is not sortable and not readable: it ranks a teenager who
  // has not played a major-league game above established stars because his row
  // was measured with a different ruler. One anchor owns the column.
  //
  // Vets get null here. The veteran warPTH field is a DIFFERENT series (the
  // if-healthy, playing-time-held path, which does strip attrition); one field
  // name, two meanings, and reading it across both populations is exactly the
  // mistake 05a25ce1 made in the other direction.
  function primeAt(m, t) {
    if (m.src !== "prospect") return null;
    const arr = m.warPTH;
    if (!arr) return null;
    const off = t - (m.eta - DATA.first_season);
    return off >= 0 && off < arr.length ? arr[off] : null;
  }
  // In-window prime total. proj_export already publishes it as warTotalPTH over
  // EXACTLY this window (_wtot sums the first HORIZON - (eta - first_season)
  // seasons, which is the span warShown paints), and it rounds the unrounded
  // series where summing the published 2-decimal cells rounds twice: Made
  // reads 15.4 from the field and 15.5 from the sum. The published field wins,
  // so the number in the cell is the number a CSV consumer joins on. The sum
  // is the fallback for a row whose prime path did not build.
  function warShownPrime(m) {
    if (m.src !== "prospect") return null;
    if (typeof m.warTotalPTH === "number") return m.warTotalPTH;
    let s = null;
    for (let t = 0; t < DATA.horizon; t++) {
      const w = primeAt(m, t);
      if (w != null) s = (s == null ? 0 : s) + w;
    }
    return s;
  }

  // Age filter bands: [lo, hi) on the row's decimal age.
  const AGE_FILTER_BANDS = { u23: [0, 23], "23-26": [23, 27], "27-30": [27, 31],
                             "31-34": [31, 35], "35+": [35, 99] };
  function posMatches(m) {
    if (state.pos === "all") return true;
    const g = posGroup(m.pos);
    // H / P side roll-ups mirror the PROSPX position filter; two-way rows
    // match both sides.
    if (state.pos === "H") return m.twoWay || !["SP", "RP"].includes(g);
    if (state.pos === "P") return m.twoWay || ["SP", "RP"].includes(g);
    return g === state.pos;
  }
  function ageMatches(m) {
    if (state.age === "all") return true;
    const b = AGE_FILTER_BANDS[state.age];
    return !!b && m.age != null && m.age >= b[0] && m.age < b[1];
  }
  function rows() {
    const all = (DATA.vets || []).concat(DATA.prospects || []);
    const q = state.q.trim().toLowerCase();
    return all.filter(m =>
      (state.src === "all" || m.src === state.src)
      && posMatches(m)
      && (state.team === "all" || m.team === state.team)
      && (state.contract === "all" || contractStatus(m).key === state.contract)
      && ageMatches(m)
      && (!q || (m.name || "").toLowerCase().includes(q)));
  }

  // The value a row sorts on, or null when it has none. Null is not a number to
  // compare: it sorts LAST in both directions (sortRows below).
  function sortVal(m, k) {
    if (k === "warTotal" || k === "rank") return warShown(m);
    if (k === "sur") return surOf(m);
    if (k === "name") return String(m.name || "");
    // Org sort (owner ask 2026-09-18): groups the board by club. A row with no
    // club returns null rather than "", so it sorts LAST in both directions per
    // the rule above instead of clumping at the top under an empty string.
    if (k === "team") return m.team ? String(m.team) : null;
    if (/^y[0-4]$/.test(k)) {
      const t = Number(k.slice(1));
      if (state.cells !== "war") {
        // Season headers sort the ACTIVE cell metric. FIP is lower-better:
        // negated so the default descending click puts the best arms first.
        const v = rateAt(m, t);
        return v == null ? null : (state.cells === "fip" ? -v : v);
      }
      return warAt(m, t);
    }
    // AAV of a contract that reaches the window. A deal ending before it (649
    // rows, often a prorated few thousand dollars) shows a dash and sorts with
    // the missing values.
    if (k === "aav") return (m.thru && m.thru >= DATA.first_season) ? (m.aav ?? null) : null;
    // The Control column sorts on the last season the club CONTROLS him, not on
    // the last season a contract guarantees him. Sorting the old `thru`
    // descending buried every cost-controlled star under every signed veteran.
    if (k === "ctrl") return ctrlThruOf(m);
    // The prime total is sortable but has no header: it is a sub-line, not a
    // column, so the sort picker is where a reader reaches it. A veteran sorts
    // null here and falls to the bottom, which is correct -- he has no prime
    // path on this anchor at all.
    if (k === "warPrime") return warShownPrime(m);
    if (["age", "thru", "warPeak", "fv", "eta", "pBust"].includes(k)) return m[k] ?? null;
    return null;
  }
  function sortRows(list) {
    const k = state.sort, dir = state.dir;
    const keyed = list.map(m => ({ m, v: sortVal(m, k), w: warShown(m) ?? -99, n: String(m.name || "") }));
    const byName = (a, b) => a.n.localeCompare(b.n, undefined, { sensitivity: "base" });
    keyed.sort((a, b) => {
      if (a.v == null || b.v == null) {
        if (a.v == null && b.v == null) return (b.w - a.w) || byName(a, b);
        return a.v == null ? 1 : -1;          // missing values last, either direction
      }
      const c = typeof a.v === "string"
        ? a.v.localeCompare(b.v, undefined, { sensitivity: "base" })
        : (a.v > b.v ? 1 : a.v < b.v ? -1 : 0);
      if (c) return dir * c;
      return (b.w - a.w) || byName(a, b);     // ties keep the board's WAR order
    });
    return keyed.map(x => x.m);
  }

  // User-tweakable scatter: BOTH axes are pickable (age, year-1 WAR, 5y WAR,
  // year-1 wOBA / wRC+ / FIP), so the one chart answers many questions -
  // aging landscape, rate-vs-WAR agreement, arm value maps. Colored by
  // contract control status. Honors the current filters; dots link to players.
  const SCATTER_AXES = {
    age:      { label: "Age",                  get: m => m.age },
    warY1:    { label: "Year-1 WAR",           get: m => warAt(m, 0) },
    warTotal: { label: "5y WAR",               get: m => warShown(m) },
    woba:     { label: "Year-1 wOBA (proj)",   get: m => (m.woba || [])[0] ?? null, f3: true },
    wrc:      { label: "Year-1 wRC+ (proj)",   get: m => (m.wrc || [])[0] ?? null },
    fip:      { label: "Year-1 FIP (proj)",    get: m => (m.fip || [])[0] ?? null, f2: true },
  };
  function _axFmt(ax, v) {
    return ax.f3 ? v.toFixed(3).replace(/^0(?=\.)/, "") : ax.f2 ? v.toFixed(2)
      : Math.abs(v) >= 100 ? String(Math.round(v)) : (Math.round(v * 10) / 10).toString();
  }
  // Talent-map dot tint by contract control status - one shared map for the
  // scatter dots AND the legend row under the axis pickers, so they never drift.
  const CONTRACT_DOT_COLORS = { signed: "var(--accent-green)", expiring: "var(--accent-gold)",
                                ctrl: "var(--accent-cyan)", nodeal: "var(--accent-lilac)",
                                prospect: "var(--text-tertiary)" };
  function projWarMap(list) {
    const ax = SCATTER_AXES[state.sx] || SCATTER_AXES.age;
    const ay = SCATTER_AXES[state.sy] || SCATTER_AXES.warY1;
    const pts = list.map(m => ({ m, x: ax.get(m), y: ay.get(m) }))
      .filter(p => p.x != null && p.y != null && isFinite(p.x) && isFinite(p.y));
    if (pts.length < 6) return "";
    const W = 760, H = 400, PAD = 52;
    const xs = pts.map(p => p.x), ys = pts.map(p => p.y);
    const _pad = (lo, hi) => { const d = (hi - lo) || 1; return [lo - 0.05 * d, hi + 0.05 * d]; };
    const [x0, x1] = _pad(Math.min(...xs), Math.max(...xs));
    const [y0, y1] = _pad(Math.min(...ys), Math.max(...ys));
    const px = v => PAD + (v - x0) / (x1 - x0) * (W - 2 * PAD);
    const py = v => (H - PAD) - (v - y0) / (y1 - y0) * (H - 2 * PAD);
    const ticks = (lo, hi) => Array.from({ length: 6 }, (_, i) => lo + (hi - lo) * i / 5);
    const grid = ticks(x0, x1).map(v => `<line x1="${px(v).toFixed(1)}" y1="${PAD}" x2="${px(v).toFixed(1)}" y2="${H - PAD}" stroke="var(--border-light)" stroke-width="0.5"/><text x="${px(v).toFixed(1)}" y="${H - PAD + 14}" text-anchor="middle" font-size="9" fill="var(--text-tertiary)">${_axFmt(ax, v)}</text>`).join("")
      + ticks(y0, y1).map(v => `<line x1="${PAD}" y1="${py(v).toFixed(1)}" x2="${W - PAD}" y2="${py(v).toFixed(1)}" stroke="var(--border-light)" stroke-width="0.5"/><text x="${PAD - 6}" y="${(py(v) + 3).toFixed(1)}" text-anchor="end" font-size="9" fill="var(--text-tertiary)">${_axFmt(ay, v)}</text>`).join("");
    // Dots are pointer shortcuts (tabindex -1): a keyboard reaches every
    // player through the board rows, not through 1,400 stops inside a role=img.
    const dots = pts.map(({ m, x, y }) => {
      const c = CONTRACT_DOT_COLORS[contractStatus(m).key] || "var(--text-tertiary)";
      const href = m.src === "prospect" ? `/prospx/#player=${encodeURIComponent(m.key)}` : `#player=${encodeURIComponent(m.key)}`;
      return `<a href="${href}" tabindex="-1"><circle cx="${px(x).toFixed(1)}" cy="${py(y).toFixed(1)}" r="3.5" fill="${c}" fill-opacity="0.7" stroke="${c}" stroke-width="0.5"><title>${esc(m.name)} - ${esc(ax.label)} ${_axFmt(ax, x)} · ${esc(ay.label)} ${_axFmt(ay, y)}</title></circle></a>`;
    }).join("");
    return `<svg viewBox="0 0 ${W} ${H}" class="proj-warmap-svg" role="img" aria-label="${esc(ay.label)} versus ${esc(ax.label)} scatter">
      <text x="${PAD}" y="20" font-size="11" font-weight="700" fill="var(--text-secondary)">${pts.length} players · ${esc(ay.label)} vs ${esc(ax.label)}</text>
      <text x="${W / 2}" y="${H - 4}" text-anchor="middle" font-size="10" fill="var(--text-tertiary)">${esc(ax.label)}</text>
      <text x="14" y="${H / 2}" text-anchor="middle" font-size="10" fill="var(--text-tertiary)" transform="rotate(-90 14 ${H / 2})">${esc(ay.label)}</text>
      ${grid}${dots}
    </svg>`;
  }

  // Prospect grade language: eFV (the outcome-grounded model grade, exported as
  // fv with fv_source="xfv") leads wherever the payload carries it, matching the
  // PROSPX board's eFV-primary treatment; consensus FV is the fallback for the
  // players eFV abstains on. Rounding rules: eFV displays round-to-NEAREST,
  // consensus FV displays CEILING (fvCeil).
  function prospectGrade(m) {
    if (m.fv_source === "xfv") return `eFV ${Math.round(m.fv)}`;
    return `Consensus FV ${EEPHUS_HUB.fvCeil(m.fv)}`;
  }
  function tagFor(m) {
    if (m.src === "prospect") {
      const gradeNote = m.fv_source === "xfv"
        // "rank-mapped to the 20-80 scale" described the QUANTILE map, which was
        // retired from display on 2026-07-25. proj_export now serves the board
        // grade (value_framework.outcome_implied_fv off the pooled outcome
        // curve), so this copy was describing a grade the row no longer carries.
        ? `Graded on eFV${m.consensus_fv != null ? `; consensus FV ${EEPHUS_HUB.fvCeil(m.consensus_fv)}` : ""}. `
        : "";
      return `<span class="proj-tag proj-tag-prospect" title="PROSPX prospect: outcome-model projection from the projected ETA. ${gradeNote}P10/P90 outcome buckets ${esc(m.bucketLo || "?")} → ${esc(m.bucketHi || "?")}; P(bust) ${m.pBust != null ? (m.pBust * 100).toFixed(0) + "%" : "?"}.">${prospectGrade(m)} · ETA ${m.eta}</span>`;
    }
    return m.twoWay
      ? `<span class="proj-tag" title="Two-way: hitting and pitching projected separately and summed per season">two-way</span>` : "";
  }

  // THE PRIME TOTAL IN THE ROW SUB LINE, and why it is a separate element from
  // the grade tag rather than more text inside it. .proj-tag is white-space:
  // nowrap and .proj-sub-tag-pros is a BLOCK that does not shrink below its
  // max-content width, so appending "prime 15.4" to the grade tag made one
  // 149px unbreakable item inside a 96px sub line, and .pc-player (overflow:
  // hidden) clipped it: measured at 390, the row read "eFV 62 - ETA 2027 -
  // prime" with the number cut off. Two wrappers are two flex items and the
  // sub line wraps between them.
  function primeTagFor(m) {
    const pr = warShownPrime(m);
    if (pr == null) return "";
    return `<span class="proj-tag proj-tag-prospect" title="Prime ${fmtWar(pr)}: P(bucket|FV)-weighted path reconciled to the prime anchor, same bust probability. Talent, not club value; board and prices use expected value.">prime ${fmtWar(pr)}</span>`;
  }
  // ONE PLACE, EVERY WIDTH, EVERY VIEW. site.css hides .proj-sub-tag-pros at
  // >= 700px in the prospect view because "the prospect set shows eFV and ETA
  // as columns; the sub-line tag repeats them, so it steps aside while they are
  // on screen". The prime tag repeats NO column -- there is no prime column in
  // either set -- so it does not step aside, and it is emitted outside that
  // wrapper. That is why the prime total is NOT also printed under the 5y
  // number: .pc-tot is 34px on a phone and clipped the label to "prim" with the
  // number cut off (measured at 390), and a second copy at wide widths would be
  // the repetition the rule above exists to prevent.
  function rowTagsHtml(m, pros) {
    if (m.src !== "prospect") return tagFor(m);
    const grade = pros ? `<span class="proj-sub-tag-pros">${tagFor(m)}</span>` : tagFor(m);
    return grade + primeTagFor(m);
  }

  // Contract control status: the Contract chip row, the scatter tint and the
  // scatter legend, all reading one function so the three cannot disagree.
  //
  // THE BUCKET ASKS THE CELL'S QUESTION, AND IT ASKS IT FIRST. Until
  // 2026-09-17 the first two tests read `thru` alone, so the answer depended on
  // the GUARANTEE and not on control: 226 rows whose contract ended in the
  // season in progress and who have no arbitration season on file at all were
  // labelled "Club control" beside Caminero, and 121 rows the club genuinely
  // holds for two more seasons (Elly De La Cruz, 2027 -> 2029) were labelled
  // "Expiring" under a tip that promised free agency. The control test now runs
  // before the guarantee tests, which is the only order that gets both right.
  //
  // `label` / `short` / `tip` are emitted for a caller that wants a rendered
  // token; the chip row and the legend carry their own fixed labels. They are
  // kept ACCURATE rather than deleted, because a stale string in an unused
  // branch is how the last one shipped.
  function contractStatus(m) {
    const first = DATA.first_season;
    if (m.src === "prospect")
      return { key: "prospect", label: "Prospect", short: "Prospect", cls: "proj-ct-prospect",
        tip: "Pre-MLB; club control starts at debut" };
    // An OPEN window with `ctrlThru == thru` belongs here too: the published
    // grid ends on a pre-arbitration season, so the platform knows there are
    // controlled seasons after the guarantee and cannot name the last one. It
    // is club control either way; only the year is unknown.
    const _ct = ctrlThruOf(m), _open = ctrlOpenOf(m);
    if (_ct != null && (_ct > (m.thru || 0) || _open))
      return { key: "ctrl", label: "Club control", short: "Club control",
        cls: "proj-ct-controlled",
        tip: _ct > (m.thru || 0)
          ? "Club-controlled past his guaranteed contract: the seasons after it are priced on the salary path, the league minimum for pre-arbitration years and the projected award for arbitration years"
          : "Club-controlled past his guaranteed contract: the published arbitration grid stops before the window does, so the seasons after it carry no price" };
    if (m.thru && m.thru > first)
      return { key: "signed", label: `Signed · ${m.thru}`, short: "Signed", cls: "proj-ct-signed",
        tip: `Guaranteed contract through ${m.thru}${m.aav ? ` at ${money(m.aav)}/yr` : ""}` };
    // Everything left with a contract is a man whose guarantee runs out inside
    // the priced window and who has no controlled season after it: the season
    // in progress (`thru < first`) counts, and used to fall through to the
    // control bucket.
    if (m.thru)
      return { key: "expiring", label: `Expiring ${m.thru}`, short: "Expiring", cls: "proj-ct-expiring",
        tip: `Last guaranteed season on file is ${m.thru}; no controlled season is priced after it` };
    return { key: "nodeal", label: "No deal", short: "No deal",
      cls: "proj-ct-controlled proj-ct-none",
      tip: "No contract and no arbitration grid on file" };
  }

  // The three top-level projection views + the unified-glossary chip (mirrors
  // the FA module's glossary link, deep-linked to the Platform & Methodology
  // group). Rendered into the filter bar on every view so switching is one
  // click and the glossary is always at hand.
  const GLOSSARY_CHIP = ` <a class="chip" href="/glossary/#cat=${encodeURIComponent("Platform & Methodology")}" title="Projection and methodology terms in the Library"><span class="chip-glyph" aria-hidden="true">${window.EephusIco ? window.EephusIco("library", 12) : ""}</span>Library</a>`;
  function viewChips(active) {
    const c = (v, label, title) =>
      `<button class="chip${active === v ? " active" : ""}" data-pv="${v}"${title ? ` title="${esc(title)}"` : ""}>${label}</button>`;
    return c("players", "Players")
      + c("teams", "Team Outlook", "Projected roster WAR (fWAR basis) rolled up to wins")
      + c("accountability", "Model Accountability", "Backtests and model verdicts")
      + GLOSSARY_CHIP;
  }

  function render() {
    const root = document.getElementById("proj-rows");
    const bar = document.getElementById("proj-filters");
    const banner = document.getElementById("proj-banner");
    if (!root || !DATA) return;
    if (state.player) { renderPlayer(state.player); return; }
    if (DATA.partial) { root.innerHTML = pxState("loading", "Loading projections."); return; }
    if (state.cmp.length === 2) { renderCompare(); return; }
    if (state.view === "teams") { renderTeams(); return; }
    if (state.view === "accountability") { renderAccountability(); return; }
    if (state.cells === "pa" && !ptLive()) state.cells = "war";
    const first = DATA.first_season;
    const teams = [...new Set((DATA.vets || []).map(m => m.team).filter(Boolean))].sort();

    const last = first + (DATA.horizon || 5) - 1;
    banner.innerHTML = `<div class="fa-note fa-sources">
      ${first}-${last} projected <span data-gl="war">WAR</span> (fWAR basis) &middot; ${DATA.n_vets} veterans, ${DATA.n_prospects} prospects
      &middot; <span data-gl="winter_dpw">$/WAR</span> ${money(DATA.dpw_usd)}${DATA.generated_at ? ` &middot; data as of ${esc(String(DATA.generated_at))}` : ""}
      &middot; <button class="chip egfx-chip" id="proj-board-gfx" title="Shareable graphic"><span class="egfx-chip-glyph" aria-hidden="true">${window.EephusIco ? window.EephusIco("gfx", 12) : ""}</span>Generate GFX</button></div>
      <details class="proj-how"><summary class="fa-sub">How this works</summary><div class="fa-note">
      Veterans: proj_lgbm_v1 on the <span data-gl="fa_projection_engine">FA projection engine</span>; /fa/ prices on its Marcel champion.${projGateSentence()}${faGateClause()}
      Prospects: <span data-gl="proj_buckets">outcome buckets</span> from their PROSPX ETA.
      Priced at the ${first} ex-ante <span data-gl="winter_dpw">$/WAR</span> ${money(DATA.dpw_usd)}${DATA.pricing_basis ? `, each season at its own level on the one written path (escalator ${(DATA.pricing_basis.g_ref * 100).toFixed(2)}%/yr, discounted at ${(DATA.pricing_basis.nominal_rate * 100).toFixed(2)}%)` : (DATA.dpw_infl ? `, escalating ${(DATA.dpw_infl * 100).toFixed(1)}%/yr` : ", flat across seasons")}.
      WAR shown: <strong>expected value</strong>, the same path <span data-gl="surplus_value">surplus</span> prices over the club control window, unsigned seasons through ${last} at most and a longer guarantee through its last season on the champion aging curve chained from the ${last} WAR.</div></details>`;
    const gfxBtn = document.getElementById("proj-board-gfx");
    if (gfxBtn) gfxBtn.onclick = () => {
      if (window.EEPHUS_GFX) window.EEPHUS_GFX.open(_projBoardSpec(sortRows(rows()).slice(0, 50)));
    };

    const chip = (label, key, field) =>
      `<button class="chip${state[field] === key ? " active" : ""}" data-pf="${field}:${key}">${label}</button>`;
    bar.innerHTML = viewChips("players") + `
      <span class="filter-label proj-fgroup">Source</span>
      ${chip("All", "all", "src")}${chip("Veterans", "vet", "src")}${chip("Prospects", "prospect", "src")}
      <span class="filter-label proj-fgroup">Pos</span>
      ${[["All", "all"], ["H", "H"], ["P", "P"], ["SP", "SP"], ["RP", "RP"], ["C", "C"], ["IF", "IF"], ["OF", "OF"], ["DH", "DH"]].map(([l, p]) => chip(l, p, "pos")).join("")}
      <span class="filter-label proj-fgroup">Age</span>
      ${[["All", "all"], ["U23", "u23"], ["23-26", "23-26"], ["27-30", "27-30"], ["31-34", "31-34"], ["35+", "35+"]].map(([l, k]) => chip(l, k, "age")).join("")}
      <span class="filter-label proj-fgroup">Contract</span>
      ${[["All", "all"], ["Signed", "signed"], ["Expiring", "expiring"], ["Club control", "ctrl"], ["No deal", "nodeal"], ["Prospect", "prospect"]].map(([l, k]) => chip(l, k, "contract")).join("")}
      <span class="filter-label proj-fgroup">Team</span>
      <select id="proj-team" class="proj-select" data-team-picker>
        <option value="all">All teams</option>
        ${teams.map(t => `<option value="${t}"${state.team === t ? " selected" : ""}>${t}</option>`).join("")}
      </select>
      <span class="filter-label proj-fgroup" title="Per-season cell metric; rate lines are veterans only">Cells</span>
      ${[["WAR", "war"], ["wRC+", "wrc"], ["wOBA", "woba"], ["FIP", "fip"]].concat(ptLive() ? [["PA/IP", "pa"]] : []).map(([l, k]) => chip(l, k, "cells")).join("")}
      <input id="proj-q" class="proj-search" type="search" placeholder="Search players…" value="${esc(state.q)}" aria-label="Search players">`;
    bar.querySelectorAll("[data-pv]").forEach(b => b.onclick = () => {
      state.view = b.dataset.pv; syncToURL(); render();
    });
    bar.querySelectorAll("[data-pf]").forEach(b => b.onclick = () => {
      const [field, key] = b.dataset.pf.split(":");
      state[field] = key; state.limit = 100;
      // A click that swaps the column set can orphan the sort (AAV has no
      // header in the prospect set): fall back to the default order.
      if (!viewSortKeys(prospectView()).includes(state.sort)) { state.sort = "warTotal"; state.dir = -1; }
      syncToURL(); render();
    });
    const sel = document.getElementById("proj-team");
    if (sel) sel.onchange = () => { state.team = sel.value; state.limit = 100; syncToURL(); render(); };
    const inp = document.getElementById("proj-q");
    if (inp) {
      inp.oninput = () => { state.q = inp.value; state.limit = 100; syncToURL(); renderTable(); };
    }
    renderTable();
    if (window.EEPHUS_GL) window.EEPHUS_GL.wire(banner);
  }

  // ---- mini trend line -------------------------------------------------------
  // SOURCE OF TRUTH: assets/fa.js `miniTrendSVG` (extracted there out of
  // dpwTrendChart, the module's $/WAR-by-winter rail chart). Same shape, same
  // contract: var() colour tokens only so it is right in both themes, endpoint
  // VALUE labels rather than an unlabelled squiggle, and an invisible fat hit
  // circle over every point so each one is hoverable. Duplicated rather than
  // imported for the reason formatMetric is duplicated at the top of this file:
  // these surfaces share no module system and /projections/ deliberately loads
  // no other module's script.
  //
  // pts: [{ v: <number>, t: <hover text> }, ...]. Returns "" under two points,
  // which is the caller's cue to render nothing rather than a one-dot chart.
  function miniTrendSVG(pts, opt) {
    const o = opt || {};
    const use = (pts || []).filter(p => p && Number.isFinite(Number(p.v)));
    if (use.length < 2) return "";
    const W = o.w || 92, H = o.h || 28;
    const PT = o.pt != null ? o.pt : 10, PB = o.pb != null ? o.pb : 4;
    const PL = o.pl != null ? o.pl : 4, PR = o.pr != null ? o.pr : 4;
    const vs = use.map(p => Number(p.v));
    let lo = Math.min(...vs), hi = Math.max(...vs);
    const span = (hi - lo) || 1;
    lo -= span * 0.08; hi += span * 0.08;
    const x = i => PL + i * (W - PL - PR) / (use.length - 1);
    const y = v => PT + (hi - v) * (H - PT - PB) / (hi - lo);
    const col = o.color || "var(--accent-cyan)";
    const fmt = o.fmt || (v => String(v));
    const line = use.map((p, i) => `${x(i).toFixed(1)},${y(p.v).toFixed(1)}`).join(" ");
    const dots = use.map((p, i) => i === use.length - 1
      ? `<circle cx="${x(i).toFixed(1)}" cy="${y(p.v).toFixed(1)}" r="2.2" fill="${col}"/>`
      : `<circle cx="${x(i).toFixed(1)}" cy="${y(p.v).toFixed(1)}" r="1.3" fill="${col}" fill-opacity="0.75"/>`).join("");
    const hits = use.map((p, i) =>
      `<circle cx="${x(i).toFixed(1)}" cy="${y(p.v).toFixed(1)}" r="6" fill="transparent"><title>${esc(p.t || "")}</title></circle>`).join("");
    const first = use[0], last = use[use.length - 1];
    const firstLbl = `<text x="${PL}" y="${Math.max(7, y(first.v) - 4).toFixed(1)}" font-size="7" fill="var(--text-tertiary)">${esc(fmt(first.v))}</text>`;
    const lastLbl = `<text x="${W - PR}" y="${Math.max(7, y(last.v) - 4).toFixed(1)}" text-anchor="end" font-size="7.5" font-weight="700" fill="var(--text-secondary)">${esc(fmt(last.v))}</text>`;
    return `<svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" class="proj-minitrend" role="img" aria-label="${esc(o.aria || "trend")}">
      <polyline points="${line}" fill="none" stroke="${col}" stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round"/>
      ${dots}${firstLbl}${lastLbl}${hits}</svg>`;
  }

  function renderTeams() {
    const root = document.getElementById("proj-rows");
    const bar = document.getElementById("proj-filters");
    const banner = document.getElementById("proj-banner");
    const rows = DATA.team_outlook || [];
    bar.innerHTML = viewChips("teams");
    bar.querySelectorAll("[data-pv]").forEach(b => b.onclick = () => {
      state.view = b.dataset.pv; syncToURL(); render();
    });
    // Banner + GFX button track the Team Outlook view (the Players banner is
    // rebuilt in render()), so Generate GFX exports the team board you're on.
    if (banner) {
      const frame = `${DATA.first_season} projected roster <span data-gl="war">WAR</span> (fWAR basis) to wins at the 47.7 replacement baseline`
        + ` &middot; <span data-gl="forward_gate">forward gate</span> on Model Accountability`;
      banner.innerHTML = `<div class="fa-note fa-sources">
        ${frame}${DATA.generated_at ? ` &middot; data as of ${esc(String(DATA.generated_at))}` : ""}
        &middot; <button class="chip egfx-chip" id="proj-teams-gfx" title="Shareable graphic"><span class="egfx-chip-glyph" aria-hidden="true">${window.EephusIco ? window.EephusIco("gfx", 12) : ""}</span>Generate GFX</button></div>`;
      const tgfx = document.getElementById("proj-teams-gfx");
      if (tgfx) tgfx.onclick = () => {
        if (window.EEPHUS_GFX && rows.length) window.EEPHUS_GFX.open(_teamOutlookBoardSpec(rows));
      };
    }
    if (!rows.length) {
      root.innerHTML = pxState("unmeasured", "Team Outlook not built yet on this deploy; the nightly build writes it.");
      return;
    }
    // Org-dashboard columns (the retired /teams/ page, merged here
    // 2026-06-12): farm rank + grade score, net active prospect surplus,
    // top prospect, and the cross-module links. Rows without a baked
    // farm block (older exports) degrade to the original columns.
    const hasFarm = rows.some(r => r.farm);
    const hasControl = rows.some(r => r.lockedPct != null || (Array.isArray(r.byYear) && r.byYear.length));
    // System Duration / Window Alignment: dark by default pre-launch; opt in
    // with #window=1 for the soak, then flip WINDOW_DEFAULT at launch. Also
    // degrades on payload presence (older exports have no etaAlignYears).
    const WINDOW_DEFAULT = true;   // surfaced: Window column on by default (#window=0 to hide)
    const _wp = new URLSearchParams((location.hash || "").replace(/^#/, "")).get("window");
    const windowOn = _wp != null ? _wp !== "0" : WINDOW_DEFAULT;
    const hasWindow = rows.some(r => (r.farm || {}).etaAlignYears != null);
    const showWindow = hasWindow && windowOn;
    // Current (2026) slate: dark-launched behind #now=1 (mirrors #window). Opt in
    // with #now=1; degrades on payload presence (older/degraded exports carry no
    // `current` block). When off, every branch below takes the existing 2027 path.
    const NOW_DEFAULT = false;
    const _np = new URLSearchParams((location.hash || "").replace(/^#/, "")).get("now");
    const nowFlag = _np != null ? _np !== "0" : NOW_DEFAULT;
    const hasNow = rows.some(r => r.current);
    const nowAvail = hasNow && nowFlag;
    // #now=1 should LAND on the Current slate the first time it's available this
    // session; a subsequent manual chip toggle (which sets teamModeTouched) then
    // sticks. The flag isn't persisted to URL (mirrors #window), so re-derive the
    // active slate every render and never trust a stale teamMode when the payload
    // is absent.
    if (nowAvail && !state.teamModeTouched) state.teamMode = "now";
    if (!nowAvail) state.teamMode = "proj";
    const nowMode = nowAvail && state.teamMode === "now";
    const curSeason = DATA.current_season || (DATA.first_season ? DATA.first_season - 1 : "");
    const pctStr = (p) => p == null ? EM_DASH : (p * 100).toFixed(1) + "%";
    const wlOf = (w, l) => `${Math.round(w)}-${Math.round(l)}`;
    // T3 runs (TM_7, class 2, dark): the exporter puts only the sides that
    // passed TM-C on the rows, so each column renders only when its key is on
    // a row. They are the first projected season on the Team Outlook frame
    // (Q9_03): the pre-free-agency frame unless the payload carries the
    // as-of-signings frame block.
    const outlookFrame = DATA.team_outlook_frame ? "as-of-signings frame" : "pre-free-agency frame";
    const runCols = [["rs", "RS", "Projected runs scored"], ["ra", "RA", "Projected runs allowed"],
                     ["runDiff", "Run diff", "Projected run differential, RS minus RA"],
                     ["pythW", "Pythag W", "Pythagenpat wins from the projected RS and RA"]]
      .filter(c => rows.some(r => r.runs && r.runs[c[0]] != null));
    const runTxt = (k, v) => {
      if (v == null || !Number.isFinite(Number(v))) return EM_DASH;
      const n = Math.round(Number(v));
      return k === "runDiff" && n > 0 ? `+${n}` : String(n);
    };
    const runCell = (r, k) => `<td class="proj-tm-run proj-cell-mono">${runTxt(k, (r.runs || {})[k])}</td>`;
    // T7 drill-down (TM_7, owner answer TM-Q4 (a), class 2, dark): a club's
    // players exactly as the roll-up counts them; renders only when the rows
    // carry `drill`.
    const hasDrill = rows.some(r => r.drill && Array.isArray(r.drill.players));
    const drillTeam = (hasDrill && state.club && rows.some(r => r.team === state.club && r.drill)) ? state.club : null;
    const drillRow = (r, ncols) => {
      const d = r.drill, f = d.foot || {};
      const np = `<span class="fa-sub">not projected</span>`;
      const sg = (v) => v == null || !Number.isFinite(Number(v)) ? np : (Number(v) > 0 ? "+" : "") + Number(v).toFixed(1);
      const w1 = (v) => v == null || !Number.isFinite(Number(v)) ? np : Number(v).toFixed(1);
      const isHit = (p) => p.side === "hit" || p.side === "two";
      const isPit = (p) => p.side === "pit" || p.side === "two";
      const ptCell = (p) => {
        const parts = [];
        if (isHit(p)) parts.push(p.pa != null ? `${Math.round(p.pa)} PA` : "PA not projected");
        if (isPit(p)) parts.push(p.ip != null ? `${Math.round(p.ip)} IP` : "IP not projected");
        return parts.join(" &middot; ");
      };
      const runsSub = (p) => {
        const bits = [];
        if (isHit(p)) bits.push(`Bat ${sg(p.bat)}`, `BsR ${sg(p.bsr)}`, `Fld ${sg(p.fld)}`, `Pos ${sg(p.posRuns)}`);
        if (isPit(p)) bits.push(`Pitching ${w1(p.pitRuns)}`);
        return bits.join(" &middot; ");
      };
      // PA and IP print only where the exposure heads serve (PJ-C's exposure
      // test); with none served the column leaves and one line says why.
      const hasPt = (d.players || []).some(p => p.pa != null || p.ip != null);
      const body = (d.players || []).map(p => `<tr>
          <td class="pd-player"><a class="fa-player-link" href="#player=${encodeURIComponent(p.key || "")}">${esc(p.name || p.key || "")}</a> <span class="fa-sub">${esc(p.pos || "")}</span><div class="pd-runs-sub fa-sub">${runsSub(p)}</div></td>
          ${hasPt ? `<td class="pd-pt fa-sub">${ptCell(p)}</td>` : ""}
          <td class="pd-run">${isHit(p) ? sg(p.bat) : ""}</td>
          <td class="pd-run">${isHit(p) ? sg(p.bsr) : ""}</td>
          <td class="pd-run">${isHit(p) ? sg(p.fld) : ""}</td>
          <td class="pd-run">${isHit(p) ? sg(p.posRuns) : ""}</td>
          <td class="pd-run">${isPit(p) ? w1(p.pitRuns) : ""}</td>
          <td>${w1(p.warComp)}</td>
          <td><strong>${w1(p.war)}</strong></td>
          <td>${sg(p.gap)}</td>
        </tr>`).join("");
      const line = (label, v, cls) => `<tr${cls ? ` class="${cls}"` : ""}><th scope="row">${label}</th><td>${v}</td></tr>`;
      const nComp = (f.nPlayers || 0) - (f.nNoComp || 0);
      const foot = `<table class="proj-drill-foot" data-proj-drill-foot><tbody>
          ${line(`Component WAR, ${nComp} players with component lines`, w1(f.warComp))}
          ${line("Gap line, served minus component", sg(f.gap))}
          ${f.nNoComp ? line(`Served WAR, ${f.nNoComp} players without component lines`, w1(f.warNoComp)) : ""}
          ${line(`Served WAR, ${f.nPlayers || 0} listed players`, w1(f.warServed), "pd-sub")}
          ${line("Champion mean minus served head (the roll-up sums the champion mean)", sg(f.champMinusServed))}
          ${line(`Arrived prospects, ${f.nProspects || 0} at their ETA`, w1(f.prospects))}
          ${line("Roster WAR", w1(f.rosterWar), "pd-total")}
        </tbody></table>`;
      const runs = (r.runs && runCols.length)
        ? `<div class="fa-sub pd-runs-line">Projected ${d.season} runs, ${outlookFrame}: ${runCols.map(c => `${c[1]} ${runTxt(c[0], r.runs[c[0]])}`).join(" &middot; ")}</div>` : "";
      const frHref = franchiseHref(r.team);
      return `<tr class="proj-detail proj-drill" data-export-skip data-drill-for="${esc(r.team)}"><td colspan="${ncols}"><div class="proj-drill-inner">
        <div class="pd-head"><strong>${esc(r.team)} ${d.season} roster, player by player</strong>${frHref ? ` &middot; <a href="${esc(frHref)}">franchise page</a>` : ""}</div>
        <div class="fa-sub">WAR is the served projection; Comp WAR and the runs are the component lines (${esc(d.frame || "FanGraphs frame")}), and the gap line is the difference. Bat, BsR, Fld and Pos are runs above average; Pitching is FIP WAR in runs above replacement.${hasPt ? "" : " PA and IP are not projected: the playing-time heads have not passed their gate."}</div>
        ${runs}
        <table class="detail-table proj-drill-table"><thead><tr><th scope="col">Player</th>${hasPt ? `<th scope="col">PA / IP</th>` : ""}<th scope="col" class="pd-run">Bat</th><th scope="col" class="pd-run">BsR</th><th scope="col" class="pd-run">Fld</th><th scope="col" class="pd-run">Pos</th><th scope="col" class="pd-run" title="FIP-based WAR in runs (FIP WAR x runs per win)">Pitching</th><th scope="col">Comp WAR</th><th scope="col">WAR</th><th scope="col">Gap</th></tr></thead>
        <tbody>${body}</tbody></table>${foot}</div></td></tr>`;
    };
    // Window cell: an arrival-curve sparkline (share of farm surplus landing
    // each 2027-31 season + a later bucket) plus etaAlignYears, colored by
    // whether the farm lands inside the controlled-core window (<= 0 aligned).
    const windowCell = (r) => {
      const f = r.farm || {};
      const a = f.etaAlignYears;
      if (a == null) return EM_DASH;
      const by = Array.isArray(f.etaByYear) ? f.etaByYear : [];
      let spark = "";
      if (by.length) {
        const mx = Math.max(0.01, ...by);
        // Only the bar HEIGHT stays inline - it is the data. Everything else
        // (width, colour, radius) is presentation and lives on .proj-eta-bar.
        spark = `<span class="proj-eta-spark">${
          by.map((v, k) => {
            const yr = DATA.first_season + k;
            const lab = k === by.length - 1 ? `${yr}+` : `${yr}`;
            const h = Math.max(2, Math.round((v / mx) * 18));
            return `<span class="proj-eta-bar" title="${esc(`${lab}: ${Math.round(v * 100)}% of farm surplus`)}" style="height:${h}px;"></span>`;
          }).join("")
        }</span> `;
      }
      const col = a <= 0 ? "var(--up)" : a >= 1.5 ? "var(--down)" : "var(--text-primary)";
      const sign = a > 0 ? "+" : "";
      const tip = `Farm surplus-weighted arrival ${f.etaMean != null ? f.etaMean : "?"} vs controlled-core WAR center ${f.coreCenter != null ? f.coreCenter : "?"}: ${a <= 0 ? "aligned" : "gap"}. Bars: share of farm surplus by arrival season.`;
      return `<span class="proj-cell-inline" title="${esc(tip)}">${spark}<span class="proj-cell-num" style="color:${col};">${sign}${a.toFixed(1)}y</span></span>`;
    };
    // ---- Current (2026) cell-builders. All read r.current (the exporter's
    // nested block) and EM_DASH per-field when absent, so a partial payload
    // degrades cleanly. No math here beyond display formatting + bar widths. ----
    const currentCell = (r) => {
      const c = r.current; if (!c || c.record == null) return EM_DASH;
      const pc = c.actualPct != null ? (c.actualPct * 100).toFixed(1) + "%" : EM_DASH;
      const gb = c.gb != null ? (c.gb === 0 ? "div lead" : `${c.gb} GB`) : "";
      const tip = `Actual ${curSeason} record: ${c.record} (${pc})${gb ? " · " + gb : ""}${c.ilOut60 ? ` · ${c.ilOut60} on the 60-day IL` : ""}.`;
      return `<span class="proj-cell-nowrap" title="${esc(tip)}"><strong>${esc(c.record)}</strong> <span class="fa-sub">${pc}</span></span>`;
    };
    const pythagCell = (r) => {
      const c = r.current; if (!c || c.pythagPct == null) return EM_DASH;
      const delta = (c.actualPct != null) ? c.actualPct - c.pythagPct : null;
      const col = delta == null ? "var(--text-primary)"
        : delta >= 0.020 ? "var(--up)" : delta <= -0.020 ? "var(--down)" : "var(--text-primary)";
      const tip = `Pythagorean expectation ${(c.pythagPct * 100).toFixed(1)}% from run differential (exp 1.83).${delta != null ? ` Actual is ${delta >= 0 ? "over" : "under"}-performing by ${Math.abs(delta * 100).toFixed(1)} pts.` : ""}`;
      return `<span class="proj-cell-mono" title="${esc(tip)}" style="color:${col};">${(c.pythagPct * 100).toFixed(1)}%</span>`;
    };
    const blendCell = (r) => {
      const c = r.current; if (!c || c.curWins == null) return EM_DASH;
      const tip = `Projected full-season ${curSeason} record: ${wlOf(c.curWins, c.curLosses)} (${(c.curPct * 100).toFixed(1)}%). Bayesian blend of the roster-talent prior (${pctStr(c.talentPriorPct)}), actual record (${pctStr(c.actualPct)}), and Pythag (${pctStr(c.pythagPct)}); weights prior/actual/pythag = ${c.blendWeights ? [c.blendWeights.prior, c.blendWeights.actual, c.blendWeights.pythag].map(x => x.toFixed(2)).join("/") : "?"} at ${c.gamesPlayed} games played.`;
      return `<span class="proj-cell-nowrap" title="${esc(tip)}"><strong>${wlOf(c.curWins, c.curLosses)}</strong> <span class="fa-sub">${(c.curPct * 100).toFixed(1)}%</span></span>`;
    };
    const playoffCell = (r) => {
      const c = r.current; if (!c || c.playoffPct == null) return EM_DASH;
      const div = c.divisionPct || 0, wc = c.wildcardPct || 0, play = c.playoffPct || 0;
      const divW = Math.round(div * 100), wcW = Math.round(wc * 100);
      const missW = Math.max(0, 100 - divW - wcW);
      // Only the segment WIDTHS stay inline - they are the odds. The track box
      // and each segment's colour live on .proj-odds-* in the stylesheet.
      const bar = `<span class="proj-odds-bar">`
        + `<span class="proj-odds-div" style="width:${divW}%;"></span>`
        + `<span class="proj-odds-wc" style="width:${wcW}%;"></span>`
        + `<span class="proj-odds-miss" style="width:${missW}%;"></span></span>`;
      const proj = (c.projWinsP10 != null && c.projWinsP90 != null)
        ? ` Projected wins ${c.projWinsMean} (80% range ${c.projWinsP10}-${c.projWinsP90}).` : "";
      const tip = `Playoff odds ${(play * 100).toFixed(0)}% = division ${(div * 100).toFixed(0)}% + wildcard ${(wc * 100).toFixed(0)}% (Monte Carlo, ${DATA.mc_schedule_source === "balanced_fallback" ? "balanced-schedule estimate" : "live remaining schedule"}).${proj}`;
      return `<span class="proj-cell-inline" title="${esc(tip)}">${bar}<span class="proj-cell-num">${(play * 100).toFixed(0)}%</span></span>`;
    };
    const sosCell = (r) => {
      const c = r.current; if (!c || c.sos == null) return EM_DASH;
      const rk = c.sosRank != null ? `#${c.sosRank}` : "";
      const col = c.sos >= 0.520 ? "var(--down)" : c.sos <= 0.480 ? "var(--up)" : "var(--text-primary)";
      const tip = `Remaining strength of schedule (log5): avg opponent talent ${(c.sos * 100).toFixed(1)}% over ${c.remGames} unplayed games; rank ${rk} (1 = hardest). Expected ~${c.remWinExp} added wins the rest of the way.`;
      return `<span class="proj-cell-mono" title="${esc(tip)}" style="color:${col};">${(c.sos * 100).toFixed(1)}% <span class="fa-sub">${rk}</span></span>`;
    };
    // Core-control cell: a decline TREND of CONTROLLED WAR per season (the
    // cliff) + the WAR-weighted lock-up %. % colored up/down; the line is drawn
    // from r.byYear, verified on the shipped payload as
    // [{season, war, wins, losses, winsRaw, depthWar, n}, ...] - `war` is the
    // controlled-WAR series this cell has always plotted.
    //
    // The bar strip this replaced was the same data with no numbers on it: you
    // could see that the core declined but not from what to what. The endpoint
    // labels are the whole point of the fa.js chart being the best small viz in
    // the tree, and they are what the control cliff most needed.
    const controlCell = (r) => {
      const by = Array.isArray(r.byYear) ? r.byYear : [];
      const pct = r.lockedPct != null ? Math.round(r.lockedPct * 100) : null;
      if (!by.length && pct == null) return EM_DASH;
      const pctCol = pct == null ? "var(--text-secondary)"
        : pct >= 75 ? "var(--up)" : pct <= 45 ? "var(--down)" : "var(--text-primary)";
      const pctStr = pct == null ? EM_DASH : `${pct}%`;
      let spark = "";
      if (by.length) {
        spark = miniTrendSVG(
          by.filter(s => s && Number.isFinite(Number(s.war)))
            .map(s => ({ v: s.war, t: `${s.season}: ${fmtWar(s.war)} controlled WAR` })),
          { color: "var(--accent-cyan)", fmt: v => fmtWar(v),
            aria: `Controlled WAR by season, ${by[0].season} to ${by[by.length - 1].season}` });
        if (spark) spark += " ";
      }
      const tip = (r.ctrlWar5y != null && r.fullWar5y != null && by.length)
        ? `${pctStr} of projected ${by[0].season}-${by[by.length - 1].season} WAR under contract, or projected controlled by age where no contract is on file (${r.ctrlWar5y} of ${r.fullWar5y}). Line: controlled WAR per season.`
        : "Share of projected WAR under contract, or projected controlled by age where no contract is on file";
      return `<span class="proj-ctrl" title="${esc(tip)}">${spark}<span class="proj-ctrl-pct" style="color:${pctCol};">${pctStr}</span></span>`;
    };
    // Click-sortable columns. `natural` = first-click direction; clicking the
    // same header again flips it (state.teamDir). Nulls always sink. Default
    // (teamSort null) preserves the export's roster-WAR ranking.
    const TEAM_SORTS = {
      team:      { get: r => r.team || "", text: true, natural: "asc" },
      war:       { get: r => r.war, natural: "desc" },
      wins:      { get: r => r.wins, natural: "desc" },
      control:   { get: r => r.lockedPct, natural: "desc" },
      window:    { get: r => (r.farm || {}).etaAlignYears, natural: "asc" },
      farm:      { get: r => (r.farm || {}).farmRank, natural: "asc" },
      surplus:   { get: r => (r.farm || {}).farmSurplusMM, natural: "desc" },
      prospect:  { get: r => ((r.farm || {}).topProspect || {}).fv, natural: "desc" },
      projected: { get: r => ((r.top || [])[0] || {}).war, natural: "desc" },
      // Current (2026) columns - only active in now-mode; additive, no collision.
      nowPct:    { get: r => (r.current || {}).actualPct, natural: "desc" },
      pythag:    { get: r => (r.current || {}).pythagPct, natural: "desc" },
      blend:     { get: r => (r.current || {}).curPct, natural: "desc" },
      playoff:   { get: r => (r.current || {}).playoffPct, natural: "desc" },
      sos:       { get: r => (r.current || {}).sos, natural: "desc" },
      // T3 runs (projected slate only; present only when the rows carry them).
      rs:        { get: r => (r.runs || {}).rs, natural: "desc" },
      ra:        { get: r => (r.runs || {}).ra, natural: "asc" },
      runDiff:   { get: r => (r.runs || {}).runDiff, natural: "desc" },
      pythW:     { get: r => (r.runs || {}).pythW, natural: "desc" },
    };
    const _sortAsc = (key) => {
      const col = TEAM_SORTS[key];
      const naturalAsc = col.natural === "asc";
      return (state.teamDir === -1) ? !naturalAsc : naturalAsc;
    };
    let viewRows = rows.slice();
    if (state.teamSort && TEAM_SORTS[state.teamSort]) {
      const col = TEAM_SORTS[state.teamSort];
      const asc = _sortAsc(state.teamSort);
      viewRows.sort((a, b) => {
        let av = col.get(a), bv = col.get(b);
        if (col.text) {
          const r = String(av || "").localeCompare(String(bv || ""));
          return asc ? r : -r;
        }
        av = (av == null || isNaN(Number(av))) ? null : Number(av);
        bv = (bv == null || isNaN(Number(bv))) ? null : Number(bv);
        if (av == null && bv == null) return 0;
        if (av == null) return 1;
        if (bv == null) return -1;
        return asc ? (av - bv) : (bv - av);
      });
    }
    const body = viewRows.map((r, i) => {
      const f = r.farm || {};
      const fmHref = farmHref(r.team);
      const farmCell = f.farmRank != null
        ? `${fmHref ? `<a href="${esc(fmHref)}" title="PROSPX farm system detail">#${f.farmRank}</a>` : `#${f.farmRank}`} <span class="fa-sub">${f.farmScore != null ? Math.round(f.farmScore) : ""}</span>`
        : EM_DASH;
      const surCell = f.farmSurplusMM != null
        ? `<span class="${f.farmSurplusMM >= 0 ? "proj-pos" : "proj-neg"}" title="Net prospect surplus NPV over the org's active prospect pool">$${Math.round(f.farmSurplusMM)}M</span>`
        : EM_DASH;
      // The grade names its basis (owner answer Q-E4): eFV once the exporter
      // serves it (fvBasis "efv"), otherwise the consensus label, printed as
      // "Consensus FV" (a payload without fvBasis predates the field and is
      // consensus).
      const topBasisEfv = f.topProspect && f.topProspect.fvBasis === "efv";
      const topCell = f.topProspect
        ? `<a class="fa-player-link" href="/prospx/#player=${encodeURIComponent(f.topProspect.key || "")}">${esc(f.topProspect.name)}</a> <span class="fa-sub" style="white-space:nowrap" data-grade-basis="${topBasisEfv ? "efv" : "consensus"}">${topBasisEfv ? "eFV" : "Consensus FV"} ${esc(String(f.topProspect.fv || "?"))}</span>`
        : EM_DASH;
      const frHref = franchiseHref(r.team);
      const openCell = `${fmHref ? `<a href="${esc(fmHref)}">farm</a> · <a href="${esc(fmHref)}&ftab=tendencies" title="Open the Org Tendencies tab">tendencies</a> · ` : ""}<a href="/fa/#view=fits&team=${encodeURIComponent(r.team)}">FA fits</a> · <a href="#team=${encodeURIComponent(r.team)}" data-team-filter="${esc(r.team)}">roster</a>${frHref ? ` · <a href="${esc(frHref)}" title="Open the club on Franchises">franchise</a>` : ""}`;
      const w = Math.round(r.wins);
      const wl = `${w}-${162 - w}`;
      const wlTip = r.depthWar != null
        ? `Roster WAR + ${r.depthWar} depth-allowance WAR over the 47.7 replacement baseline (league recentered to 2,430 total wins${r.winsRaw != null ? `; raw roster-only read ${Math.round(r.winsRaw)} wins` : ""})`
        : `Roster WAR over the 47.7 replacement baseline`;
      if (nowMode) {
        // Current (2026) slate: actual record / Pythag / blended projection /
        // playoff odds / remaining SOS. Team + rank columns are shared.
        return `<tr>
      <td>${i + 1}</td>
      <td class="proj-player">${clubA(r.team, `${logoMark(r.team)}<strong>${esc(r.team)}</strong>`)}</td>
      <td>${currentCell(r)}</td>
      <td>${pythagCell(r)}</td>
      <td>${blendCell(r)}</td>
      <td>${playoffCell(r)}</td>
      <td>${sosCell(r)}</td>
    </tr>`;
      }
      const drillBtn = (hasDrill && r.drill)
        ? ` <button type="button" class="proj-drill-btn" data-export-skip data-drill="${esc(r.team)}" aria-expanded="${drillTeam === r.team ? "true" : "false"}" aria-label="${esc(`${drillTeam === r.team ? "Hide" : "Show"} the ${r.team} roster breakdown`)}" title="Player by player">&#9662;</button>`
        : "";
      return `<tr>
      <td>${i + 1}</td>
      <td class="proj-player">${clubA(r.team, `${logoMark(r.team)}<strong>${esc(r.team)}</strong>`)}${drillBtn}</td>
      <td class="proj-war ${EephusTiers.cls(r.war, "rosterWar")}">${r.war.toFixed(1)}</td>
      <td title="${esc(wlTip)}"><strong>${wl}</strong></td>${runCols.map(c => runCell(r, c[0])).join("")}
      ${hasControl ? `<td>${controlCell(r)}</td>` : ""}
      ${showWindow ? `<td>${windowCell(r)}</td>` : ""}
      ${hasFarm ? `<td>${farmCell}</td><td>${surCell}</td><td>${topCell}</td>` : ""}
      <td class="fa-sub">${(r.top || []).map(p => `<a class="fa-player-link" href="#player=${encodeURIComponent(p.key)}">${esc(p.name)}</a> ${p.war.toFixed(1)}`).join(" · ")}</td>
      ${hasFarm ? `<td class="fa-sub proj-cell-nowrap">${openCell}</td>` : ""}
    </tr>${drillTeam === r.team ? drillRow(r, "__PROJ_NCOLS__") : ""}`;
    }).join("");
    const note = nowMode
      ? `Current (${curSeason}) slate <span class="eephus-beta">β beta</span>: Bayesian blend of the roster-talent prior, actual record and Pythagorean record (RS/RA); the prior fades as games are played. Playoff odds: Monte Carlo over ${DATA.mc_schedule_source === "balanced_fallback" ? "a balanced-schedule estimate (live schedule unavailable)" : "the live remaining schedule"}. SOS: log5 opponent talent over unplayed games (1 = hardest). Does not change the projection board.`
      : `${hasControl ? `Core control: WAR-weighted share of each org's projected ${DATA.first_season}-${DATA.first_season + (DATA.horizon || 5) - 1} production under contract, or projected controlled by age where no contract is on file; the sparkline is controlled WAR per season.` : ""}${hasFarm ? " Farm columns come from the PROSPX org models." : ""}`;
    // Sortable header: click to sort by it, click again to flip direction.
    // The active column shows a ▲/▼ arrow reflecting the effective direction.
    const _arrow = (key) => state.teamSort === key
      ? ` <span class="proj-sort-arrow">${_sortAsc(key) ? "▲" : "▼"}</span>` : "";
    const sth = (key, label, title) =>
      `<th class="proj-sortable" data-team-sort="${key}"${title ? ` title="${esc(title)}"` : ""}>${label}${_arrow(key)}</th>`;
    // Mode sub-chips (only when the current-season payload is available + opted in).
    const modeChips = nowAvail
      ? `<div class="proj-mode-chips">
        <button class="chip${!nowMode ? " active" : ""}" data-team-mode="proj">Projected (${DATA.first_season})</button>
        <button class="chip${nowMode ? " active" : ""}" data-team-mode="now">Current (${curSeason})</button></div>`
      : "";
    const header = nowMode
      ? `<thead><tr><th>#</th>${sth("team", "Team")}${sth("nowPct", "Record", `Actual ${curSeason} record + win%`)}${sth("pythag", "Pythag", "Pythagorean win% from run differential (exp 1.83)")}${sth("blend", "Proj W-L", "Bayesian blend of talent prior + actual + Pythag -> projected full-season record")}${sth("playoff", "Playoff odds", "Monte-Carlo division/wildcard/playoff probability")}${sth("sos", "Rem SOS", "Remaining strength of schedule via log5 (rank 1 = hardest)")}</tr></thead>`
      : `<thead><tr><th>#</th>${sth("team", "Team")}${sth("war", "Roster WAR", "Sum of each rostered veteran's year-1 champion mean WAR (the Marcel path /fa/ prices; quantile points never summed) plus arrived prospects. Top projected prints the quantile-head path, so a name there can differ from his share here.")}${sth("wins", "Proj W-L", "Projected record, league-recentered (depth allowance over the rostered universe)")}${runCols.map(c => sth(c[0], c[1], `${c[2]}, ${DATA.first_season}, ${outlookFrame}; component runs on FanGraphs' frame`).replace('class="proj-sortable"', 'class="proj-sortable proj-tm-run"')).join("")}${hasControl ? sth("control", "Core control", `WAR-weighted share of projected ${DATA.first_season}-${DATA.first_season + (DATA.horizon || 5) - 1} WAR under contract, or projected controlled by age where no contract is on file. Not the club control window; that is on the players board.`) : ""}${showWindow ? sth("window", `<span data-gl="window_alignment">Window</span>`, "Farm arrival vs the controlled-core window; negative = aligned") : ""}${hasFarm ? `${sth("farm", "Farm", "PROSPX farm-system rank + grade score")}${sth("surplus", "Farm surplus", "Net prospect surplus NPV over the org's active prospect pool")}${sth("prospect", "Top prospect", "Sort by the grade printed beside the top prospect (eFV, or Consensus FV where it says so)")}` : ""}${sth("projected", "Top projected", "Sort by the org's top projected player WAR")}${hasFarm ? "<th>Open</th>" : ""}</tr></thead>`;
    // The Current slate keeps its note above the table (it says what changes
    // under the reader); the projected slate's column notes fold under it.
    const noteTop = nowMode ? `<div class="fa-note proj-teams-note">${note}</div>` : "";
    const noteFold = (!nowMode && note.trim())
      ? `<details class="proj-how"><summary class="fa-sub">How this works</summary><div class="fa-note proj-teams-note">${note}</div></details>` : "";
    const nCols = (header.match(/<th[\s>]/g) || []).length;
    const runsNote = (!nowMode && runCols.length)
      ? `<div class="fa-sub proj-runs-frame">${runCols.map(c => c[1]).join(", ")}: ${DATA.first_season}, ${outlookFrame}; component runs on FanGraphs' frame.</div>` : "";
    root.innerHTML = `${modeChips}${noteTop}${runsNote}
      <table class="detail-table proj-table">
      ${header}
      <tbody>${body.split('"__PROJ_NCOLS__"').join(`"${nCols}"`)}</tbody></table>${noteFold}`;
    root.querySelectorAll("[data-team-sort]").forEach(h => h.onclick = () => {
      const k = h.dataset.teamSort;
      if (state.teamSort === k) state.teamDir = state.teamDir === -1 ? 1 : -1;
      else { state.teamSort = k; state.teamDir = 1; }
      renderTeams();
    });
    root.querySelectorAll("[data-team-mode]").forEach(b => b.onclick = () => {
      const m = b.dataset.teamMode;
      if (m === state.teamMode) return;
      // Switching slates: the two modes have disjoint sortable columns, so clear
      // any active sort to avoid a stale key pointing at a now-hidden column.
      // teamModeTouched pins the user's choice over the #now=1 auto-land default.
      state.teamMode = m; state.teamModeTouched = true;
      state.teamSort = null; state.teamDir = 1;
      renderTeams();
    });
    root.querySelectorAll("[data-drill]").forEach(b => b.onclick = (ev) => {
      ev.preventDefault();
      const t = b.dataset.drill;
      state.club = state.club === t ? null : t;
      syncToURL(); renderTeams();
    });
    root.querySelectorAll("[data-team-filter]").forEach(a => a.onclick = (ev) => {
      ev.preventDefault();
      state.view = "players"; state.team = a.dataset.teamFilter;
      syncToURL(); render();
    });
    if (window.EEPHUS_GL) { window.EEPHUS_GL.wire(root); if (banner) window.EEPHUS_GL.wire(banner); }
  }

  // ===========================================================================
  // Model Accountability (#view=accountability) - the projection models'
  // owner-committed verdicts + methodology (data/model_registry.json) with the
  // held-out backtest receipts read verbatim from the committed eval artifacts
  // (proj_export._accountability_block). Pure surfacing: the audit ledger is the
  // single source of truth, nothing is recomputed here. The numbers shown match
  // the committed *_eval.json files byte-for-byte.
  // ===========================================================================
  const VERDICT_META = {
    validated:   { label: "Validated",   col: "var(--accent-green)" },
    provisional: { label: "Provisional", col: "var(--accent-gold)" },
    unvalidated: { label: "Unvalidated", col: "var(--down)" },
    deprecated:  { label: "Deprecated",  col: "var(--text-tertiary)" },
  };
  const VERDICT_DESC = {
    validated: "forward-chained backtest beats the baseline",
    provisional: "measured, but partially (short window or descriptive)",
    unvalidated: "predictive claim with no measurement yet",
    deprecated: "failed validation, retired",
  };
  function verdictBadge(v) {
    const m = VERDICT_META[v] || { label: v || "?", col: "var(--text-tertiary)" };
    // Only `background` stays inline: it is a computed VALUE (the verdict's own
    // colour). Shape, type and the on-badge text colour live on .proj-verdict.
    return `<span class="proj-verdict" style="background:${m.col};">${esc(m.label)}</span>`;
  }
  function _num(v, d) {
    return v == null || !Number.isFinite(Number(v)) ? EM_DASH : Number(v).toFixed(d == null ? 2 : d);
  }
  function _signed(v, d) {
    if (v == null || !Number.isFinite(Number(v))) return EM_DASH;
    const n = Number(v);
    return (n >= 0 ? "+" : "") + n.toFixed(d == null ? 2 : d);
  }
  function _pct0(v) {
    return v == null || !Number.isFinite(Number(v)) ? EM_DASH : (Number(v) * 100).toFixed(0) + "%";
  }

  // Team win totals - the retro backtest per season for the arm that serves
  // (served_arm, picked by the ship decision) beside the prior-wins
  // carry-forward, MAE and r both, + the player-level pooled read, the ship
  // gate, and the still-pending forward gate.
  function teamWinsTable(tw) {
    if (!tw || !(tw.per_season || []).length) return "";
    const rows = tw.per_season.map(s => `<tr>
      <td>${s.season}${s.is_holdout ? ` <span class="proj-tag" title="Held out of the cohort-intercept fit" data-gl="holdout">holdout</span>` : ""}</td>
      <td>${s.n_assigned_players ?? EM_DASH}</td>
      <td class="proj-acct-key">${_num(s.mae)}</td>
      <td>${_num(s.r)}</td>
      <td class="fa-sub">${_num(s.baseline_mae)}</td>
      <td class="fa-sub">${_num(s.baseline_r)}</td>
    </tr>`).join("");
    const fg = tw.forward_gate || {};
    const pooled = tw.player_pooled || {};
    const sd = tw.ship_decision || {};
    const hm = sd.holdout_mae || {};
    const armLabel = tw.served_arm === "cohort_recentered"
      ? "cohort intercepts + recentering" : "uniform recentering";
    const gate = sd.holdout_season
      ? ` Ship gate on the ${sd.holdout_season} holdout: cohort intercepts ${_num(hm.cohort_recentered)} vs uniform recentering ${_num(hm.recentered)}; `
        + (sd.challenger_wins ? "intercepts serve." : "uniform recentering serves, intercepts not served.")
        + ` Prior-wins carry-forward ${_num(hm.baseline_prior_wins)}.`
      : "";
    const vintage = tw.retro_generated_at ? ` Retro backtest run ${esc(String(tw.retro_generated_at))}.` : "";
    return `<table class="detail-table proj-table proj-acct-table">
      <thead><tr><th>Season</th><th title="Players assigned to their actual season team">Roster n</th>
        <th title="Mean absolute error in projected team wins, ${armLabel} roll-up (the served arm; lower is better)"><span data-gl="mae">MAE</span> (wins)</th>
        <th title="Correlation of projected vs actual wins, ${armLabel} roll-up">r</th>
        <th title="Prior-season wins carry-forward baseline MAE">Baseline</th>
        <th title="Prior-season wins carry-forward baseline correlation with actual wins">Baseline r</th></tr></thead>
      <tbody>${rows}</tbody></table>
      <div class="fa-sub proj-acct-foot">Rows score the served roll-up (${armLabel}). Player-level engine pooled bias ${_signed(pooled.bias_act_minus_pred)} WAR, MAE ${_num(pooled.mae)} (n=${pooled.n ?? "?"}).${gate}${vintage}</div>
      <div class="fa-note proj-acct-foot"><span data-gl="forward_gate">Forward gate</span>: ${esc(fg.status || "pending")}; ${esc(fg.scope || "first season only")}; first scoreable ${esc(fg.first_scoreable || "end of the 2027 season")}. ${esc(fg.metric || "")}</div>`;
  }

  // Veteran WAR paths - the touched-once 2022-24 holdout, champion vs baseline
  // per horizon (MAE + bias + P10-P90 coverage). Holdout labels mature only
  // through h4, so the table runs as deep as the artifact reports.
  function vetHorizonsTable(vh, pending) {
    const ch = (vh && vh.champion && vh.champion.horizons) || [];
    if (!ch.length) return "";
    const bl = (vh.baseline && vh.baseline.horizons) || [];
    const blByH = {}; bl.forEach(r => { blByH[r.h] = r; });
    const rows = ch.map(r => {
      const b = blByH[r.h] || {};
      return `<tr>
        <td>h${r.h}</td>
        <td class="proj-acct-key">${_num(r.mae)}</td>
        <td class="fa-sub">${b.mae != null ? _num(b.mae) : EM_DASH}</td>
        <td>${_signed(r.bias)}</td>
        <td>${_pct0(r.coverage)}</td>
        <td class="fa-sub">${b.coverage != null ? _pct0(b.coverage) : EM_DASH}</td>
      </tr>`;
    }).join("");
    return `<table class="detail-table proj-table proj-acct-table">
      <thead><tr><th title="Projection horizon, seasons ahead">Horizon</th>
        <th title="Champion mean absolute WAR error (lower is better)"><span data-gl="mae">MAE</span></th>
        <th title="Baseline MAE" class="fa-sub">Baseline</th>
        <th title="Mean error, actual minus predicted">Bias</th>
        <th title="Share of actuals inside the P10-P90 band (target ~80%)"><span data-gl="p10_p90_bands">Coverage</span></th>
        <th title="Baseline coverage" class="fa-sub">Baseline cov.</th></tr></thead>
      <tbody>${rows}</tbody></table>
      <div class="fa-sub proj-acct-foot">${esc(vh.frame || "")} Champion ${esc((vh.champion || {}).model || "")} vs prior baseline ${esc((vh.baseline || {}).model || "")}${pending ? `: ${esc(pending)}` : ""}.</div>`;
  }

  // Prospect post-ETA paths - forward-chained debut cohorts: the FV-only
  // scouting-consensus champion vs the MiLB-stats challenger that lost.
  function prospectPathsTable(pp) {
    if (!pp || !pp.champion) return "";
    const c = pp.champion, ch = pp.challenger || {};
    return `<table class="detail-table proj-table proj-acct-table">
      <thead><tr><th>Model</th><th>n</th><th><span data-gl="mae">MAE</span> (WAR)</th><th title="Rank correlation vs realized first-3y WAR (the ship metric)">Spearman</th></tr></thead>
      <tbody>
        <tr><td>${esc(c.label || "champion")} <span class="proj-tag">champion</span></td><td>${c.n ?? EM_DASH}</td><td>${_num(c.mae)}</td><td class="proj-acct-key">${_num(c.spearman, 3)}</td></tr>
        <tr><td class="fa-sub">${esc(ch.label || "challenger")}</td><td>${ch.n ?? EM_DASH}</td><td>${_num(ch.mae)}</td><td>${_num(ch.spearman, 3)}</td></tr>
      </tbody></table>
      <div class="fa-sub proj-acct-foot">Forward-chained debut cohorts ${esc((pp.scored_years || []).join(", "))}. Stat-line challengers lost the pre-registered dual gate and are recorded as losses.</div>`;
  }

  // Board spec for the Generate GFX modal on the Model Accountability view:
  // the owner-committed model-verdict ledger (model, surface, metric, verdict
  // badge) straight from data/model_registry.json - the same rows the cards
  // below render. Verdict colour: validated green, provisional muted,
  // deprecated/unvalidated red (a non-validated warning state).
  function _accountabilityBoardSpec(models) {
    const vcol = { validated: "green", provisional: "muted", deprecated: "red", unvalidated: "red" };
    const rows = models.map(m => {
      const vl = VERDICT_META[m.verdict] ? VERDICT_META[m.verdict].label : (m.verdict || "?");
      return { cells: [
        { t: m.label || m.model_id || "?" },
        { t: m.surface || EM_DASH, c: "muted" },
        { t: m.metric || EM_DASH },
        { t: vl, c: vcol[m.verdict] || "muted", bold: true },
      ] };
    });
    const acct = DATA.accountability || {};
    const checked = lastChecked(acct);
    return {
      kind: "board", module: "MLB Projections", accentToken: "--accent-cyan",
      title: "MLB Projections · Model Accountability",
      subtitle: `${models.length} projection models`
        + (checked ? ` · verdicts checked ${checked}` : ""),
      url: "eephus.io/projections", filenameBase: "eephus-projections-accountability",
      caption: "Model registry verdicts · receipts from the committed eval artifacts",
      board: { defaultCount: 25, counts: [10, 25, 50], legend: "verdict per model_registry", columns: [
        { label: "Model", frac: 0.28 },
        { label: "Surface", frac: 0.28 },
        { label: "Metric", frac: 0.30, wideOnly: true },
        { label: "Verdict", frac: 0.14 },
      ], rows },
    };
  }

  // The registry's `version` is the date its schema was cut (2026-06-11), not
  // when a verdict was last read, so printing it beside "as of" told a reader
  // the verdicts were three months old (M05-09). The date a reader needs is the
  // newest last_checked across the rows this view shows.
  function lastChecked(acct) {
    const ds = (acct.models || []).map(m => m.last_checked).filter(Boolean).map(String).sort();
    return ds.length ? ds[ds.length - 1] : null;
  }

  function renderAccountability() {
    const root = document.getElementById("proj-rows");
    const bar = document.getElementById("proj-filters");
    const banner = document.getElementById("proj-banner");
    const acct = DATA.accountability || {};
    bar.innerHTML = viewChips("accountability");
    bar.querySelectorAll("[data-pv]").forEach(b => b.onclick = () => {
      state.view = b.dataset.pv; syncToURL(); render();
    });
    if (banner) {
      const acctGfxChip = ((acct.models || []).length && window.EEPHUS_GFX)
        ? ` &middot; ${window.EEPHUS_GFX.chipHTML("proj-acct-gfx", "Generate GFX")}` : "";
      banner.innerHTML = `<div class="fa-note fa-sources">
        Registry <span data-gl="model_verdict">verdicts</span> and held-out <span data-gl="backtest">backtests</span> as committed, not recomputed
        ${lastChecked(acct) ? `&middot; verdicts last checked ${esc(lastChecked(acct))}` : ""}${acct.generated_at ? ` &middot; as of ${esc(String(acct.generated_at))}` : ""}${acctGfxChip}</div>`;
    }
    const models = acct.models || [];
    if (!models.length) {
      root.innerHTML = pxState("unmeasured", "Model Accountability not built yet on this deploy; the nightly build writes it.");
      if (window.EEPHUS_GL && banner) window.EEPHUS_GL.wire(banner);
      return;
    }
    const bt = acct.backtests || {};
    const tableFor = (art, m) => {
      if (art === "data/team_outlook_eval.json") return teamWinsTable(bt[art]);
      if (art === "data/proj_horizon_eval.json") return vetHorizonsTable(bt[art], m.remeasure_pending);
      if (art === "data/prospect_path_eval.json") return prospectPathsTable(bt[art]);
      return "";
    };
    const legend = (acct.verdict_enum || []).map(v =>
      VERDICT_META[v] ? `<span class="proj-acct-legend-item">${verdictBadge(v)} <span class="fa-sub">${esc(VERDICT_DESC[v] || "")}</span></span>` : "")
      .filter(Boolean).join(`<span class="fa-sub" aria-hidden="true"> &middot; </span>`);
    const glHref = `/glossary/#cat=${encodeURIComponent("Platform & Methodology")}`;
    const cards = models.map(m => {
      const fresh = m.last_checked
        ? `last checked ${esc(String(m.last_checked))}${m.artifact_age_days != null ? ` &middot; artifact ${m.artifact_age_days}d old` : ""}${m.stale ? ` &middot; <span class="proj-neg">stale</span>` : ""}`
        : "";
      return `<div class="mlbp-section proj-acct-card">
        <div class="proj-acct-head">
          <span class="mlbp-section-title">${esc(m.label)}</span> ${verdictBadge(m.verdict)}${m.remeasure_pending ? ` <span class="fa-sub proj-acct-pending">${esc(m.remeasure_pending)}</span>` : ""}
        </div>
        ${m.summary ? `<div class="fa-note proj-acct-summary">${esc(m.summary)}</div>` : ""}
        <div class="fa-sub proj-acct-predicts">${esc(m.predicts || "")}</div>
        <details class="proj-how"><summary class="fa-sub">Champion, baseline and metric</summary><div class="proj-acct-meta">
          <strong>Champion</strong> ${esc(m.champion || "?")}<br>
          <strong>Baseline</strong> <span class="fa-sub">${esc(m.baseline || "?")}</span><br>
          <strong>Metric</strong> <span class="fa-sub">${esc(m.metric || "?")}</span>
        </div></details>
        ${tableFor(m.eval_artifact, m)}
        ${m.notes ? `<details class="proj-acct-notes"><summary class="fa-sub">Lab log</summary><div class="fa-note">${esc(m.notes)}</div></details>` : ""}
        ${fresh ? `<div class="fa-sub proj-acct-fresh">${fresh} &middot; <a href="${glHref}">methodology in the Library</a></div>` : ""}
      </div>`;
    }).join("");
    root.innerHTML = `<div class="mlbp-page">
      <details class="proj-how"><summary class="fa-sub">What the verdicts mean</summary><div class="proj-acct-legend">${legend}</div></details>
      ${cards}</div>`;
    const agfx = document.getElementById("proj-acct-gfx");
    if (agfx) agfx.onclick = () => {
      if (window.EEPHUS_GFX && models.length) window.EEPHUS_GFX.open(_accountabilityBoardSpec(models));
    };
    if (window.EEPHUS_GL) { if (banner) window.EEPHUS_GL.wire(banner); window.EEPHUS_GL.wire(root); }
  }

  // ===========================================================================
  // Players board: ONE <table> (2026-09-11, owner ask). One row per player, a
  // sticky header, the five seasons aligned under their own headers, every sort
  // key on its own header.
  //
  // FIT, NOT SCROLL. table-layout:fixed at width:100% cannot be wider than its
  // box, so the page never scrolls sideways. Columns leave by BOARD width
  // (site.css, @container projboard), never the five seasons: AAV first, then
  // the rank, then Age and Thru fold into the Player sub line, then the numbers
  // tighten. Hidden cells stay in the DOM, so the CSV is the same at every
  // width, and the row detail line carries every folded fact.
  // ===========================================================================

  // Logo in front of the team code, which follows it as text. Decorative: a
  // failed load removes the image instead of printing the code twice.
  function logoMark(org) {
    if (!org) return "";
    return `<img class="fa-logo" src="${esc(teamLogoSrc(org))}" alt="" loading="lazy" onerror="this.remove()">`;
  }

  // ---- the salary path strip (ask C, 2026-09-16) -----------------------------
  // The year-by-year salary the surplus was priced on, which is literally what
  // the owner asked for: surplus "relative to their projected arbitration
  // amounts". It renders in the OPEN-ROW detail here and under the Surplus tile
  // on the MLB player card, and NEVER in the always-visible board row - measured
  // at 390px it costs 3 lines and 177px there.
  //
  // Every cell state is a state the payload already carries, so nothing here
  // infers anything:
  //   is-ros   the rest-of-season leg (surRos)          solid border
  //   is-guar  src "contract"                           solid border
  //   is-est   src "arb_ladder" / "class_closure"       DASHED border
  //   is-cut   at or past salCut                        dashed, salary struck
  //   is-fa    the first season past salThru            only when salTrunc null
  //   is-unk   rendered INSTEAD of is-fa when salTrunc  the window is not known
  // The dashed border is the board's existing .proj-ct-est idiom, reused so
  // "estimated, not signed" reads the same way in both places.
  //
  // is-fa is SUPPRESSED whenever salTrunc is set. A row whose Spotrac grid is
  // pre-arbitration-only has no established control end, and printing
  // "2029 FA / not controlled" for it would be a served falsehood: 266 veterans
  // are in exactly that state.
  function salText(usd) {
    if (usd == null) return EM_DASH;
    if (usd < 5e4) return "<$0.1M";
    if (usd < 1e6) return `$${(usd / 1e6).toFixed(2)}M`;
    return money(usd);
  }
  function salaryStripHtml(m, opt) {
    const path = m && m.salPath;
    if (!path || !path.length || !DATA) return "";
    const o = opt || {};
    const first = DATA.first_season, H = DATA.horizon;
    const sur = m.sur || [];
    const opts = {};
    (m.salOpt || []).forEach(x => { opts[x[0]] = x[1]; });
    // The club's right (owner answer VAL2-Q2): a club option season the club
    // would decline on the mean path prices at $0, never below.
    const decl = new Set((m.salOptDecl || []).map(Number));
    const cells = [];
    const dTxt = (v) => v == null ? "" :
      `<span class="sp-d ${v >= 0 ? "proj-pos" : "proj-neg"}">${(v >= 0 ? "+" : "") + money(v * 1e6)}</span>`;
    if (m.surRos != null)
      cells.push(`<span class="proj-sp-c is-ros"><span class="sp-y">rest of ${first - 1}</span>`
        + `<span class="sp-s">${m.rosWar != null ? `${fmtWar(m.rosWar)} WAR` : "in progress"}</span>`
        + dTxt(m.surRos) + `</span>`);
    path.forEach(st => {
      const s = st[0], usd = st[1], tok = st[4] || "", src = st[5], cut = !!st[6];
      const t = s - first;
      const cls = cut ? "is-cut" : (src === "contract" ? "is-guar" : "is-est");
      const opn = opts[s];
      const yr = cut ? `${s} not tendered`
        : (opn === "club" && decl.has(s)) ? `${s} club option, declined`
        : opn ? `${s} ${opn} option`
        : src === "contract" ? `${s} signed` : `${s} ${tok.toLowerCase()}`;
      const wTail = (t >= H && Array.isArray(m.warTail)) ? m.warTail[t - H] : null;
      const lTail = (t >= H && Array.isArray(m.warP10Tail)) ? m.warP10Tail[t - H] : null;
      const hTail = (t >= H && Array.isArray(m.warP90Tail)) ? m.warP90Tail[t - H] : null;
      const bTail = (lTail != null && hTail != null)
        ? ` (P10 ${war1(lTail)} / P90 ${war1(hTail)}, the ${first + H - 1} P10 and P90 chained the same way, the P10 not floored at zero)` : "";
      const tip = cut
        ? "Carrying him through the rest of his arbitration years costs more than he is worth, so the club walks away here"
        : (opn === "club" && decl.has(s)) ? "Club option season the club would decline: the salary is above his value on the mean path, so it prices at $0, never below (declining is the club's right)"
        : opn === "club" ? "Club option season the club would exercise: it prices as guaranteed salary, worth more than it costs on the mean path"
        : opn ? "Priced as if the player stays; an opt out is not modelled"
        : (src === "contract" && t >= H)
        ? `Guaranteed salary on file; this season prices ${wTail != null ? `${fmtWar(wTail)} WAR` : "the WAR"} on the champion (Marcel) aging curve chained from the ${first + H - 1} WAR, past the five seasons the board prints${bTail}`
        : src === "class_closure" ? "Arbitration year implied by the last class token on the board, not listed by Spotrac yet"
        : src === "arb_ladder" ? (tok.toUpperCase().indexOf("PRE") === 0
            ? "Pre-arbitration season at the CBA league minimum: a rule, not a prediction"
            : "Projected arbitration award")
        : "Guaranteed salary on file";
      cells.push(`<span class="proj-sp-c ${cls}" title="${esc(tip)}"><span class="sp-y">${esc(yr)}</span>`
        + `<span class="sp-s">${salText(usd)}</span>`
        + (cut ? `<span class="sp-d">not tendered</span>` : dTxt(sur[t])) + `</span>`);
    });
    const lastS = first + H - 1;
    if (m.salTrunc) {
      const why = m.salTrunc === "no_prior_salary"
        ? "no prior salary on file, arbitration years not priced"
        : "control end unknown";
      cells.push(`<span class="proj-sp-c is-unk" title="${esc(why)}">`
        + `<span class="sp-y">${(m.salThru || lastS) + 1}+</span>`
        + `<span class="sp-s">window not established</span><span class="sp-d">${esc(why)}</span></span>`);
    } else if (m.salThru != null && m.salThru < lastS) {
      cells.push(`<span class="proj-sp-c is-fa"><span class="sp-y">${m.salThru + 1} FA</span>`
        + `<span class="sp-s">free agent</span><span class="sp-d">not controlled</span></span>`);
    }
    if (!cells.length) return "";
    return `<div class="proj-sp${o.cls ? " " + o.cls : ""}" role="group" aria-label="Salary path">`
      + `<span class="proj-sp-h"><b data-gl="salary_path">Salary path</b></span>`
      + cells.join("") + `</div>`;
  }

  // One decimal, never "-0.0" (a P10 of -0.04 would print that).
  function war1(v) { return v == null ? EM_DASH : fmtWar(Math.round(v * 10) / 10 || 0); }
  // A 2026 salary can be a prorated few thousand dollars; money() would say $0.0M.
  function aavText(usd) { return usd == null ? EM_DASH : (usd < 5e4 ? "<$0.1M" : money(usd)); }
  // THE CONTROL WINDOW, READ ONCE. `ctrlThru` is stamped by
  // salary_path.control_end and copied verbatim into every payload; nothing on
  // this page recomputes max(thru, salThru), which is how the site came to
  // carry five answers to one question. The fallback exists only so a payload
  // exported before 2026-09-17 still paints a coherent cell.
  function ctrlThruOf(m) {
    if (m.ctrlThru != null) return m.ctrlThru;
    const v = Math.max(m.thru || 0, m.salThru || 0);
    return v || null;
  }
  function ctrlOpenOf(m) { return m.ctrlThru != null ? !!m.ctrlOpen : !!m.salTrunc; }
  // WHAT THE UNSIGNED SEASONS ARE, NAMED ONCE. A pre-arbitration salary is the
  // CBA league minimum - a rule, not a prediction - and an arbitration salary
  // is the board's projected award. The glossary says exactly that and the
  // salary path strip four rows below labels each season with its own token,
  // so the one-sentence disclosure may not call the whole span "projected
  // arbitration salaries": on 397 rows, the owner's named row among them, the
  // span opens with a PRE-ARB season. The split is read off `salPath`, which
  // every row that has a span also carries.
  function unsignedSpanText(m, from, to) {
    let pre = false, arb = false;
    (m.salPath || []).forEach(st => {
      const s = st[0];
      if (s < from || s > to || st[5] === "contract") return;
      if (String(st[4] || "").toUpperCase().indexOf("PRE") === 0) pre = true; else arb = true;
    });
    const span = from >= to ? `${to} is` : `${from}-${to} are`;
    if (pre && arb)
      return `${span} unsigned club-controlled seasons: the CBA league minimum for the pre-arbitration years, the projected award for the arbitration years.`;
    if (pre)
      return `${span} unsigned pre-arbitration seasons at the CBA league minimum, which is a rule and not a signed salary.`;
    if (arb)
      return `${span} projected arbitration salaries, not signed.`;
    return `${span} unsigned club-controlled seasons.`;
  }
  // The second sentence of an OPEN cell, by the reason the window is open. One
  // string, so the board cell, the card block and the PROSPX chip cannot give
  // three accounts of the same row.
  function ctrlOpenReason(why, ct) {
    return why === "no_prior_salary"
      ? "No season of the window carries a salary to raise the first arbitration award from, so the seasons after it are not priced."
      : `The published arbitration grid ends on a pre-arbitration season, so the first arbitration season is unknown and the seasons after ${ct} are not priced.`;
  }
  function ctrlEstOf(m) {
    return m.ctrlThru != null ? !!m.ctrlEst
      : (m.salThru != null && (!m.thru || m.salThru > m.thru));
  }

  // THE CONTROL CELL (2026-09-17, replacing the Thru cell).
  //
  // The cell prints the last season the CLUB CONTROLS him and the sub-line
  // prints the guarantee. It used to be the other way round, and that is the
  // owner's report: a cell reading 2026 sat four columns from a Surplus cell
  // whose own tooltip said "contracted seasons plus projected arbitration
  // seasons", which is two window lengths stated at once on one row. The badge
  // that qualified it rendered eight columns away in the Player cell and was
  // stripped from the CSV, so the reader read the cell.
  //
  // THE DISCLOSURE RULE, WITH NO EXCEPTION: the words "signed" and
  // "guaranteed" belong to `thru` and are never attached to `ctrlThru`. The
  // projected part of the span is marked three ways, strongest first: a dashed
  // border (the idiom the salary path strip on this same page already taught
  // the reader), a sub-line naming the guarantee (it survives a screenshot, a
  // print stylesheet and a colour-blind reader), and a tip naming the seasons.
  //
  // `sub` is the Control cell's second line. `fold` is what the Player cell
  // shows once the column folds below 700px, so a phone keeps the fact.
  function ctPill(m) {
    const first = DATA.first_season, lastS = first + DATA.horizon - 1;
    if (m.src === "prospect")
      return { text: "Prospect", sub: "starts at debut", fold: "prospect",
        cls: "proj-ct-prospect",
        tip: "Pre-MLB. Club control starts at his debut and is priced from his projected ETA over the 7-season valuation window." };
    const ct = ctrlThruOf(m);
    const cutNote = m.salCut != null
      ? ` The model projects the club declines to tender him for ${m.salCut}, so surplus stops after ${m.salCut - 1}.` : "";
    if (ct == null)
      return { text: "none", sub: "no deal on file", fold: "no deal on file",
        cls: "proj-ct-controlled proj-ct-none",
        tip: m.ctrlWhy === "no_prior_salary"
          ? "No contract on file, and no season of the window carries a salary to raise a first arbitration award from, so nothing is priced for this player."
          : "No contract and no arbitration grid on file. Surplus is not priced for this player." };
    const est = ctrlEstOf(m), open = ctrlOpenOf(m);
    const why = m.ctrlWhy || (m.salTrunc || null);
    // THE BRANCHES ARE ORDERED BY INFORMATION, NOT BY BASIS. `!est` used to run
    // first, so a row whose window is OPEN but whose path prices nothing past
    // the guarantee (the grid ends on a pre-arbitration token, 2 rows today)
    // printed a solid "2028 / guaranteed / No arbitration seasons are on file
    // after it" here while its own player-card Contract tab printed "2028+" and
    // called the year a floor. A grid that ends on a PRE-ARB token guarantees
    // that arbitration seasons follow, so the sentence was also false on its
    // own terms. `open` is the stronger statement and it goes first.
    if (open) {
      return { text: `${ct}+`, sub: m.thru ? `guar. ${m.thru}` : "no deal on file",
        fold: m.thru ? `${ct}+ · guar. ${m.thru}` : `${ct}+ · no deal`,
        cls: `proj-ct-controlled proj-ct-open${est ? " proj-ct-est" : ""}`,
        tip: `Club control through at least ${ct}. ${ctrlOpenReason(why, ct)}${cutNote}` };
    }
    if (!est) {
      // Control ends where the guarantee ends: the cell is a CONTRACT fact, so
      // it is solid and it uses the guarantee word. `m.thru` is always set here
      // (est is false only when the path prices nothing past it).
      const rate = m.aav ? ` at ${money(m.aav)}/yr` : "";
      const tail = why === "horizon"
        ? ` Surplus prices the ${first}-${lastS} horizon only.`
        : why === "closure_buyout"
        ? " The contract buys out his whole published arbitration grid, so no arbitration season follows it."
        : " No arbitration seasons are on file after it.";
      const _tpC = why === "horizon" ? null : pricedTail(m);
      const tailP = _tpC ? ` Surplus prices every guaranteed season, ${_tpC.from}-${_tpC.end} on the champion aging curve chained from the ${_tpC.from - 1} WAR.` : "";
      return { text: String(ct), sub: "guaranteed", fold: `guaranteed ${m.thru}`,
        cls: "proj-ct-signed",
        tip: `Guaranteed through ${m.thru}${rate}.${tail}${tailP}${cutNote}` };
    }
    const guar = m.thru
      ? `Guaranteed through ${m.thru}${m.aav ? ` at ${money(m.aav)}/yr` : ""}; ${unsignedSpanText(m, m.thru + 1, ct)}`
      : "No guaranteed contract on file.";
    // A HORIZON ROW ON AN ESTIMATED BASIS NAMES A FLOOR, NOT AN END. The year
    // is where the five-season window stopped, not where control stops, so the
    // plain-year rule (which belongs to the contract-only case above, and to
    // the 39 nine-figure deals that run past the horizon) would state a fact
    // the platform has not established. 0 rows today; the assertion that the
    // population stays empty is in test_control_window.py, and this branch is
    // what keeps the empty population from being the only thing standing
    // between a reader and a false year.
    if (why === "horizon")
      return { text: `${ct}+`, sub: m.thru ? `guar. ${m.thru}` : "no deal on file",
        fold: m.thru ? `${ct}+ · guar. ${m.thru}` : `${ct}+ · no deal`,
        cls: "proj-ct-controlled proj-ct-est proj-ct-open",
        tip: `Club control through at least ${ct}; the board prices the ${first}-${lastS} horizon only. ${guar}${cutNote}` };
    return { text: String(ct), sub: m.thru ? `guar. ${m.thru}` : "no deal on file",
      fold: m.thru ? `${ct} · guar. ${m.thru}` : `${ct} · no deal`,
      cls: "proj-ct-controlled proj-ct-est",
      tip: m.thru
        ? `Club control through ${ct}. ${guar}${cutNote}`
        : `Club control through ${ct} on unsigned club-controlled seasons. ${guar}${cutNote}` };
  }
  // Row detail line: every fact a folded column carried, plus the ones no
  // column carries (per-season bands, the expected path surplus prices, the
  // surplus split). Emitted only for open rows. Its first cell spans the
  // columns that never fold (Player, 5y, Surplus, the first three seasons);
  // every foldable column gets a pad carrying its own fold class, so the row
  // always paints exactly as many cells as the header does at every width (a
  // colspan past the painted columns adds phantom columns to a fixed table
  // and crushes the Player column).
  const OPEN = new Set();
  function detailRowHtml(m, pros) {
    const first = DATA.first_season, H = DATA.horizon;
    const g = (label, body, gl) => `<span class="proj-dt-g"><b${gl ? ` data-gl="${gl}"` : ""}>${label}</b> ${body}</span>`;
    const bands = Array.from({ length: H }, (_, t) => {
      const s = first + t, lo = bandAt(m, t, "lo"), hi = bandAt(m, t, "hi");
      if (lo == null || hi == null) return `${s} ${m.src === "prospect" && s < m.eta ? "MiLB" : EM_DASH.trim()}`;
      return `${s} ${war1(lo)}/${war1(hi)}`;
    }).join(" &middot; ");
    const parts = [];
    if (m.src === "prospect") {
      parts.push(g("eFV", m.fv_source === "xfv" ? String(Math.round(m.fv)) : `FV ${EEPHUS_HUB.fvCeil(m.fv)}`, "xfv"));
      if (m.consensus_fv != null) parts.push(g("FV", String(EEPHUS_HUB.fvCeil(m.consensus_fv)), "consensus_fv"));
      parts.push(g("ETA", esc(m.eta ?? EM_DASH)));
      if (m.pBust != null) parts.push(g("P(bust)", `${(m.pBust * 100).toFixed(0)}%`, "bust_prob"));
      if (m.bucketLo || m.bucketHi) parts.push(g("Outcomes", `${esc(m.bucketLo || "?")} to ${esc(m.bucketHi || "?")}`, "proj_buckets"));
      // Both anchors, named, one beside the other. The group says which series
      // each number is on, because the two differ only by anchor and a bare pair
      // of numbers would not say that.
      const _pr = warShownPrime(m);
      if (_pr != null)
        parts.push(g(`Prime ${H}y`, `${fmtWar(_pr)} on the prime (talent) anchor &middot; ${fmtWar(warShown(m))} expected, which is the column and the priced path`));
      if (m.warPeak != null) parts.push(g("Peak", fmtWar(m.warPeak)));
      parts.push(g("P10/P90", bands, "p10_p90_bands"));
    } else {
      parts.push(g("P10/P90", bands, "p10_p90_bands"));
      if (m.warTotal != null) parts.push(g(`Expected ${H}y`, fmtWar(m.warTotal), "ewar"));
      // The Contract group is where a reader goes for the whole contract
      // picture, so it carries BOTH facts and keeps them apart by name: the
      // guarantee is a signed deal, the club control end is not.
      const _ctY = ctrlThruOf(m);
      const ctGuar = m.thru && m.thru >= first && m.aav != null ? `guaranteed ${m.thru} at ${money(m.aav)}/yr`
        : m.thru ? `guaranteed ${m.thru}, salary ${aavText(m.aav)}`
        : m.salPath ? "no guaranteed contract on file" : "none on file";
      const ctCtrl = (_ctY != null && _ctY !== m.thru)
        ? ` · club control ${_ctY}${ctrlOpenOf(m) ? "+" : ""}` : "";
      parts.push(g("Contract", `${ctGuar}${ctCtrl}`));
      const sv = surOf(m);
      const ros = m.surTotal != null ? m.surTotal - (m.surNpv || 0) : null;
      // ASK C: the group names the CONTROL WINDOW, because that is now what the
      // number covers - the seasons a club still holds him for, at whatever the
      // path says each one costs, not only the ones a contract prices.
      // Gated on the two cases where "through YYYY" would be a claim the
      // platform cannot make: an OPEN window (the grid stopped early) says "at
      // least", and a horizon-clamped row says nothing at all, because its
      // number is a statement about our five seasons and not about the player.
      const _ctW = ctrlThruOf(m);
      const _tl = horizonTail(m);
      const _tp = _tl ? null : pricedTail(m);
      const thruTxt = _tl ? ` (${_tl.first}-${_tl.end} only. ${horizonTailText(m, _tl)})`
        : _tp ? ` (club control window through ${_ctW}. ${pricedTailText(_tp)})`
        : _ctW == null || m.ctrlWhy === "horizon" ? ""
        : ctrlOpenOf(m) ? ` (club control window through at least ${_ctW})`
        : ` (club control window through ${_ctW})`;
      const split = sv == null ? "not priced"
        : (ros != null && m.surNpv != null) ? `${money(sv)} = rest of ${first - 1} ${money(ros)} + ${first}+ ${money(m.surNpv)}${thruTxt}`
        : (ros != null) ? `${money(sv)}, rest of ${first - 1} only`
        : `${money(sv)}, ${first}+${thruTxt}`;
      parts.push(g("Surplus", split, "surplus_value"));
      if (m.surSalLo != null && m.surSalHi != null)
        parts.push(g("If the award lands", `${money(m.surSalLo)} to ${money(m.surSalHi)}`, "salary_path"));
      if (m.rosWar != null) parts.push(g(`Rest of ${first - 1}`, `${fmtWar(m.rosWar)} WAR`));
      const line = (arr, fmt) => arr.map(v => v == null ? EM_DASH.trim() : fmt(v)).join(" ");
      if ((m.wrc || []).some(v => v != null)) parts.push(g("wRC+", line(m.wrc, RATE_META.wrc.fmt), "wrc_plus"));
      if ((m.fip || []).some(v => v != null)) parts.push(g("FIP", line(m.fip, RATE_META.fip.fmt), "fip"));
      if (m.twoWay && m.warHit && m.warPit) {
        const sum = a => a.reduce((x, y) => x + (y || 0), 0);
        parts.push(g("Two-way", `hit ${fmtWar(sum(m.warHit))} + pit ${fmtWar(sum(m.warPit))} (expected)`));
      }
    }
    const pad = c => `<td class="${c} proj-dt-pad" aria-hidden="true"></td>`;
    const tail = [`pc-y pc-y${H - 2}`, `pc-y pc-y${H - 1}`, "pc-age"]
      .concat(pros ? ["pc-fv", "pc-eta", "pc-peak", "pc-bust"] : ["pc-aav", "pc-ct"]);
    return `<tr class="proj-detail" id="projd-${esc(m.key)}" data-export-skip>${pad("pc-rank")}`
      + `<td colspan="${1 + H}" class="proj-dt-cell"><div class="proj-dt">${parts.join("")}${pros ? "" : salaryStripHtml(m)}</div></td>`
      + tail.map(pad).join("") + `</tr>`;
  }

  function renderTable() {
    const root = document.getElementById("proj-rows");
    const first = DATA.first_season;
    const H = DATA.horizon;
    const list = sortRows(rows());
    const seasons = Array.from({ length: H }, (_, t) => first + t);
    const pros = prospectView();
    if (state.cells === "pa" && !ptLive()) state.cells = "war";
    const cellLbl = state.cells === "war" ? "WAR" : RATE_META[state.cells].label;

    // Header cell: a real <th scope=col> carrying aria-sort (valid on a
    // columnheader) around a native <button>: Enter and Space with no keydown
    // shim. data-export-text keeps the arrow and the short forms out of the CSV.
    const th = (key, label, cls, title, exportText) => {
      const on = state.sort === key;
      const aria = on ? (state.dir < 0 ? "descending" : "ascending") : "none";
      return `<th scope="col" class="${cls}" aria-sort="${aria}" data-export-text="${esc(exportText)}">`
        + `<button type="button" class="proj-sort" data-psort="${key}" title="${esc(title)}">${label}`
        + `<span class="proj-sort-ind" aria-hidden="true">${on ? (state.dir < 0 ? "▾" : "▴") : ""}</span></button></th>`;
    };
    // .proj-sr-sm stays in the accessible name and leaves the screen at phone
    // width, so "27" reads "2027" and "5y" reads "5y WAR" to a screen reader.
    const head = `<thead><tr>`
      + th("rank", "#", "pc-rank", "Board position under the current sort", "#")
      + th("name", "Player", "pc-player", "Sort by name", "Player")
      + `<th class="pc-csv" hidden data-export-text="Pos"></th><th class="pc-csv" hidden data-export-text="Team"></th>`
      // THE ANCHOR IS ON THE HEADER, not only in the tooltip: one column, one
      // anchor, for every row in every view. A prospect row publishes a second
      // total on the prime anchor, and it is carried under its own name (the 5y
      // cell sub-line, the row tag, the detail line and its own CSV column),
      // never mixed into this one.
      + th("warTotal", `${H}y<span class="proj-sr-sm"> WAR</span><span class="proj-th-unit">expected</span>`, "pc-tot",
          "Projected WAR (fWAR basis, the training label) over the window on the expected path, which is the path surplus prices. Prospects carry a second, prime-anchored total beside it, labelled prime.", `${H}y WAR (expected)`)
      // Export-only: the prospect prime total, so the anchor the sub-line carries
      // survives a CSV. Empty on a veteran row, which has no prime path.
      + `<th class="pc-csv" hidden data-export-text="Prime ${H}y WAR (prospects, talent anchor)"></th>`
      + th("sur", "Surplus", "pc-sur",
          `Veterans: value minus salary over the club control window through ${first + H - 1}; a guarantee past ${first + H - 1} prices to its end on the champion (Marcel) aging curve; an unsigned season past ${first + H - 1} carries no price. Prospects: eFV surplus, 7 seasons from ETA.`, "Surplus")
      + seasons.map((s, t) => th("y" + t,
          `<span class="proj-sr-sm">${String(s).slice(0, 2)}</span>${String(s).slice(2)}`
            + (state.cells === "war" ? "" : `<span class="proj-th-unit">${esc(cellLbl)}</span>`),
          `pc-y pc-y${t}`, `Sort by ${s} (${cellLbl})`, `${s} ${cellLbl}`)).join("")
      + th("age", "Age", "pc-age", "Age on the projection row", "Age")
      + (pros
        ? th("fv", "eFV", "pc-fv", "eFV, rounded to nearest; consensus FV fallback rounds up", "eFV")
          + th("eta", "ETA", "pc-eta", "Projected MLB arrival season", "ETA")
          + th("warPeak", "Peak", "pc-peak", "Per-year WAR at peak age on the talent path; surplus does not use it", "Peak WAR")
          + th("pBust", "P(bust)", "pc-bust", "Probability the outcome lands in the bust bucket", "P(bust)")
        : th("aav", "AAV", "pc-aav", "AAV of the guaranteed contract on file", "AAV")
          // A tooltip cannot travel in a CSV, so the guarantee and the basis
          // become export-only columns beside the visible Control year. They
          // are `hidden`, which keeps them out of the layout and out of the
          // header/detail column count, and innerText on an unrendered cell
          // falls back to textContent, which is what the scraper reads.
          + `<th class="pc-csv" hidden data-export-text="Guaranteed thru"></th>`
          + th("ctrl", "Control", "pc-ct",
              "Last season the club controls him. The seasons past the guaranteed contract are unsigned club-controlled seasons: the CBA league minimum for pre-arbitration years, the projected award for arbitration years.", "Control thru")
          + `<th class="pc-csv" hidden data-export-text="Control basis"></th>`)
      + `</tr></thead>`;

    const body = list.slice(0, state.limit).map((m, i) => {
      const isPros = m.src === "prospect";
      const href = isPros ? `/prospx/#player=${encodeURIComponent(m.key)}` : `#player=${encodeURIComponent(m.key)}`;
      const ct = ctPill(m);
      const seasonCells = seasons.map((s, t) => {
        const td = inner => `<td class="pc-y pc-y${t}">${inner}</td>`;
        const gap = () => td(`<span class="proj-dim">${isPros && s < m.eta ? "MiLB" : EM_DASH}</span>`);
        if (state.cells !== "war") {
          const v = rateAt(m, t);
          if (v == null) return gap();
          const mm = RATE_META[state.cells];
          if (state.cells === "pa") {
            // A two-way row prints his PA and names the IP beside it.
            const pt = [m.pa != null ? `${Math.round(m.pa)} PA` : "", m.ip != null ? `${Math.round(m.ip)} IP` : ""].filter(Boolean).join(" and ");
            return td(`<span class="proj-war" title="${s}: ${pt} projected, the component lines' playing time (FanGraphs frame). Display only; WAR and pricing are unaffected.">${mm.fmt(v)}</span>`);
          }
          return td(`<span class="proj-war ${rateClass(v)}" title="${s}: ${esc(mm.tip)}. Display only; WAR and pricing are unaffected.">${mm.fmt(v)}</span>`);
        }
        const w = warAt(m, t);
        if (w == null) return gap();
        const lo = bandAt(m, t, "lo"), hi = bandAt(m, t, "hi");
        // The number is the expected path for every row. The COLOUR is ranked
        // within the row's own population (see warLadder), so the cell says so
        // rather than leaving a reader to infer that a prospect and a veteran
        // painted the same green mean the same WAR. They mean the same rank.
        const _pw = primeAt(m, t);
        return td(`<span class="proj-war ${EephusTiers.cls(w, warLadder(m))}" title="${s}: ${fmtWar(w)} WAR (expected path, fWAR basis)${lo != null ? ` &middot; P10 ${war1(lo)} / P90 ${war1(hi)}` : ""}${_pw != null ? ` &middot; prime ${fmtWar(_pw)} (talent anchor)` : ""}${isPros ? " &middot; colour ranks him in the prospect pool" : ""}">${fmtWar(w)}</span>`);

      }).join("");
      // Vets: the expected-value total. Prospects: the in-window sum of the
      // shown cells. The Total P10-P90 band stays withdrawn (F-01).
      // The colour on this cell ranks the PER-SEASON AVERAGE of the seasons the
      // row paints, not the sum, so the reader is told which number the colour
      // is about. Same words for every row, no tier word, no em dash.
      // A prospect and a veteran read the SAME anchor in this column. What they
      // do not share is the pool the colour ranks them in, and the prospect row
      // publishes a second total the veteran row has no analogue for, so its
      // tooltip names both and the cell prints the second one under the first.
      const primeTot = warShownPrime(m);
      const totTip = (isPros
        ? `Sum of the in-window seasons shown, on the expected path: the path surplus prices${primeTot != null ? `. Prime ${fmtWar(primeTot)} is the same P(bucket|FV)-weighted path reconciled to the prime anchor: talent, not what a club collects, and no dollar reads it` : ""}`
        : `Expected path, which is also what surplus prices${m.warTotalPTH != null ? `; if he holds his playing time, ${fmtWar(m.warTotalPTH)}` : ""}`)
        + (isPros ? ". Colour ranks the per-season average against the prospect pool"
                  : ". Colour ranks the per-season average of the seasons shown");
      const sv = surOf(m);
      const _tlS = isPros ? null : horizonTail(m);
      const _tpS = (isPros || _tlS) ? null : pricedTail(m);
      const surTip = isPros
        ? "Prospect surplus: the eFV surplus the Trade Machine board serves for him, over the 7-season valuation window from his projected ETA (not repriced here)"
        : _tlS
        ? `${m.surRos != null ? "Rest of this season plus " : ""}NPV of (convex production value − salary) over ${_tlS.first}-${_tlS.end} only, not the whole club control window. ${horizonTailText(m, _tlS)}`
        : _tpS
        ? `${m.surRos != null ? "Rest of this season plus " : ""}NPV of (convex production value − salary) over the whole guarantee, ${_tpS.first}-${_tpS.end}. ${pricedTailText(_tpS)}`
        : (m.surRos != null && m.surNpv == null
            ? `Rest-of-season control only: ${Math.round((m.rosFrac || 0) * 100)}% of ${first - 1} left, prorated projection minus prorated salary`
            : (m.surRos != null
                ? "Rest of this season plus NPV of (convex production value − salary) over the club control window"
                : "NPV of (convex production value − salary) over the club control window"))
          + (m.salSrc === "contract+arb"
              ? ". Club control window: contracted seasons plus projected arbitration seasons"
              : m.salSrc === "arb_projection" || m.salPath
              ? ". Club control window: the salary path. Arbitration seasons are projected"
              : "")
          + (m.salCut != null ? `. Not tendered from ${m.salCut}` : "");
      // Surplus is a RANKED value, not a sign: 100 / 50 / 20 / 5 / 1 $M plus the red
      // step under zero. The cut at 1 exists because unpriced and expiring rows print
      // "$0.x", and it moves 38.1% of the pool out of the ink tier without touching the
      // default view (measured 35.4 + 1.0 against a single 36.4).
      const sur = sv != null ? `<span class="${EephusTiers.cls(sv / 1e6, "surplus")}" title="${surTip}">${money(sv)}</span>` : EM_DASH;
      const aav = (m.aav != null && m.thru && m.thru >= first) ? money(m.aav) : EM_DASH;
      const age = m.age != null ? Math.floor(m.age) : EM_DASH;
      const inCmp = state.cmp.includes(m.key);
      const open = OPEN.has(m.key);
      const cmpBtn = `<button type="button" class="proj-cmp-btn${inCmp ? " active" : ""}" data-cmp-key="${esc(m.key)}" aria-pressed="${inCmp}" aria-label="Compare ${esc(m.name)}" title="${inCmp ? "Remove from compare" : "Compare head-to-head (pick two players)"}">${window.EephusIco ? window.EephusIco("compare", 12) : ""}</button>`;
      const xpBtn = `<button type="button" class="proj-xp-btn" data-xp-key="${esc(m.key)}" aria-expanded="${open}"${open ? ` aria-controls="projd-${esc(m.key)}"` : ""} aria-label="Details: ${esc(m.name)}" title="Details">▾</button>`;
      // Sub line: position and team as TEXT (the CSV and a screen reader get
      // the org), then the facts whose columns fold at narrow widths (CSS shows
      // them only then), then the row tags and the async FA chip.
      // The club links to its club page (owner ask 9): a prospect's to his farm
      // system, a veteran's to Franchises. The row's own click handler skips
      // links, so the club link never opens the row's detail line.
      const sub = `<span class="proj-pl-sub"><span class="proj-sub-id">${esc(m.pos || "")}${m.team ? ` &middot; ${clubA(m.team, `${logoMark(m.team)}${esc(m.team)}`, { ctx: isPros ? "farm" : "franchise" })}` : " &middot; FA"}</span>`
        + `<span class="proj-sub-age">age ${age}</span>`
        + (isPros ? "" : `<span class="proj-sub-ct ${ct.cls}" title="${esc(ct.tip)}">${esc(ct.fold)}</span>`)
        + rowTagsHtml(m, pros)
        + (DATA.n_fa != null ? faChip(m) : `<span class="proj-fa-slot" data-fa-key="${esc(m.key)}"></span>`) + `</span>`;
      const tail = pros
        ? `<td class="pc-fv"><span title="${m.fv_source === "xfv" ? `Graded on eFV${m.consensus_fv != null ? `; consensus FV ${EEPHUS_HUB.fvCeil(m.consensus_fv)}` : ""}` : "Consensus FV (eFV abstains)"}">${isPros ? (m.fv_source === "xfv" ? Math.round(m.fv) : `FV ${EEPHUS_HUB.fvCeil(m.fv)}`) : EM_DASH}</span></td>`
          + `<td class="pc-eta">${m.eta ?? EM_DASH}</td>`
          + `<td class="pc-peak">${m.warPeak != null ? fmtWar(m.warPeak) : EM_DASH}</td>`
          + `<td class="pc-bust"><span title="Outcome buckets ${esc(m.bucketLo || "?")} to ${esc(m.bucketHi || "?")}">${m.pBust != null ? (m.pBust * 100).toFixed(0) + "%" : EM_DASH}</span></td>`
        : `<td class="pc-aav">${aav}</td>`
          + `<td class="pc-csv" hidden>${m.thru != null ? m.thru : ""}</td>`
          // data-export-text on the CELL, because the scraper reads the cell's
          // innerText and the sub-line is part of it: without this the CSV
          // column would read "2030 guar. 2026" in one field. The guarantee has
          // its own column beside it. A row with no control end exports EMPTY,
          // never "none" and never 0.
          + `<td class="pc-ct" data-export-text="${esc(ctrlThruOf(m) != null ? ct.text : "")}">`
          + `<span class="proj-ct ${ct.cls}" title="${esc(ct.tip)}">${esc(ct.text)}</span>`
          + (ct.sub ? `<span class="proj-ct-sub" title="${esc(ct.tip)}">${esc(ct.sub)}</span>` : "")
          + `</td>`
          + `<td class="pc-csv" hidden>${esc(m.salSrc && m.salSrc !== "pending" ? m.salSrc : "")}</td>`;
      return `<tr data-key="${esc(m.key)}"${isPros ? ' class="is-prospect"' : ""}>`
        + `<td class="pc-rank">${i + 1}</td>`
        + `<th scope="row" class="pc-player" data-export-text="${esc(m.name)}"><div class="proj-pl">${rowPhoto(m)}`
        + `<a class="fa-player-link mlb-name proj-pl-name" href="${esc(href)}" title="${esc(m.name)}">${esc(m.name)}</a>${cmpBtn}${xpBtn}${sub}</div></th>`
        + `<td class="pc-csv" hidden>${esc(m.pos || "")}</td><td class="pc-csv" hidden>${esc(m.team || "")}</td>`
        // The ladder is the ROW'S ladder, not always "war". Measured on the
        // served board: 182 of the 183 prospect totals painted one colour,
        // because a bucket-weighted expected path averages 0.4 to 1.5 a season
        // and the war ladder's bottom cut is 1.5. warProspect was added for the
        // season cells on 2026-09-18 and never reached this cell. No veteran
        // total changes colour (warLadder returns "war" for every vet row) and
        // no printed number moves.
        + `<td class="pc-tot"><span class="proj-tot ${EephusTiers.clsAvgInk(warShown(m), nPainted(m), warLadder(m))}" title="${esc(totTip)}">${fmtWar(warShown(m))}</span></td>`
        + `<td class="pc-csv" hidden>${primeTot != null ? fmtWar(primeTot) : ""}</td>`
        + `<td class="pc-sur">${sur}</td>`
        + seasonCells
        + `<td class="pc-age">${age}</td>`
        + tail
        + `</tr>`
        + (open ? detailRowHtml(m, pros) : "");
    }).join("");

    const _wm = projWarMap(list);
    const _axSel = (id, cur, name) => `<select id="${id}" class="proj-select proj-select-ax" aria-label="${name}">
      ${Object.entries(SCATTER_AXES).map(([k, ax]) => `<option value="${k}"${cur === k ? " selected" : ""}>${esc(ax.label)}</option>`).join("")}</select>`;
    const _ay = (SCATTER_AXES[state.sy] || SCATTER_AXES.warY1).label;
    const _ax2 = (SCATTER_AXES[state.sx] || SCATTER_AXES.age).label;
    const warMapLegend = `<div class="proj-warmap-legend">
        <span class="proj-warmap-legend-lede">dot color = contract status</span>
        ${[["signed", "Signed"], ["expiring", "Expiring"], ["ctrl", "Club control"], ["nodeal", "No deal"], ["prospect", "Prospect"]].map(([k, l]) =>
          `<span class="proj-legend-item"><span class="proj-legend-dot" style="background:${CONTRACT_DOT_COLORS[k]};" aria-hidden="true"></span>${l}</span>`).join("")}
      </div>`;
    const warMap = _wm ? `<details class="proj-warmap"><summary>Scatter &middot; ${esc(_ay)} vs ${esc(_ax2)} (current filters &middot; pick any axes)</summary>
      <div class="proj-warmap-axes">
        <label for="proj-sy">Y</label>${_axSel("proj-sy", state.sy, "Y axis")}<label for="proj-sx">X</label>${_axSel("proj-sx", state.sx, "X axis")}
      </div>
      ${warMapLegend}
      <div class="proj-warmap-wrap" data-export-chart data-export-title="${esc(_ay)} vs ${esc(_ax2)}">${_wm}</div></details>` : "";
    function projBoardSidebar(curr) {
      // No Scope module: the lede above the board carries the same four facts.
      const warTot = m => warShown(m) ?? -99;
      const topWar = curr.slice().sort((a, b) => warTot(b) - warTot(a)).slice(0, 6);
      const warRow = m => `<div class="fa-rail-row"><a class="fa-player-link" href="${m.src === "prospect" ? `/prospx/#player=${encodeURIComponent(m.key)}` : `#player=${encodeURIComponent(m.key)}`}">${esc(m.name)}</a><span class="fa-rail-num">${fmtWar(warTot(m))}</span></div>`;
      const warMod = `<div class="fa-rail-mod"><div class="fa-rail-head" title="Top ${DATA.horizon}-year projected WAR (fWAR basis) among the current filters (expected path)">Top projected WAR</div>
        ${topWar.map(warRow).join("")}</div>`;
      const surList = curr.filter(m => surOf(m) != null).sort((a, b) => (surOf(b) || 0) - (surOf(a) || 0)).slice(0, 6);
      const surRow = m => `<div class="fa-rail-row"><a class="fa-player-link" href="${m.src === "prospect" ? `/prospx/#player=${encodeURIComponent(m.key)}` : `#player=${encodeURIComponent(m.key)}`}">${esc(m.name)}</a><span class="fa-rail-num ${surOf(m) >= 0 ? "proj-pos" : "proj-neg"}">${money(surOf(m))}</span></div>`;
      const surMod = surList.length ? `<div class="fa-rail-mod"><div class="fa-rail-head" title="Largest surplus among the current filters">Best surplus</div>
        ${surList.map(surRow).join("")}</div>` : "";
      const groups = {};
      curr.forEach(m => { const g = posGroup(m.pos); groups[g] = (groups[g] || 0) + 1; });
      const supply = Object.entries(groups).sort((a, b) => b[1] - a[1])
        .map(([g, n]) => `<div class="fa-rail-row"><span>${esc(g)}</span><span class="fa-rail-num">${n}</span></div>`).join("");
      const supplyMod = supply ? `<div class="fa-rail-mod"><div class="fa-rail-head" title="Current filtered pool by position group">Pool supply</div>${supply}</div>` : "";
      return `<aside class="fa-board-rail">${warMod}${surMod}${supplyMod}</aside>`;
    }
    // Sort vocabulary: one table for the eyebrow cue, the picker and its
    // reverse button. The cue is the only on-screen sign of a sort whose column
    // has folded at this width.
    const SORT_LBL = { rank: `${H}y WAR`, name: "Name", team: "Org", warTotal: `${H}y WAR`, sur: "Surplus", age: "Age",
      aav: "AAV", ctrl: "Club control thru", fv: "eFV", eta: "ETA", warPeak: "Peak WAR",
      warPrime: `Prime ${H}y WAR`, pBust: "P(bust)" };
    seasons.forEach((s, t) => { SORT_LBL["y" + t] = `${s} ${cellLbl}`; });
    const sortName = SORT_LBL[state.sort] || SORT_LBL.warTotal;
    const arrow = state.dir < 0 ? "▾" : "▴";
    const dirWord = (state.sort === "name" || state.sort === "team") ? (state.dir > 0 ? "A-Z" : "Z-A") : (state.dir < 0 ? "high first" : "low first");
    const boardHead = `<div class="newsprint-eyebrow" style="margin-top:4px;">
      <span class="newsprint-eyebrow-label">${H}-Year Projection Board</span>
      <span class="newsprint-eyebrow-meta">${seasons[0]}-${seasons[seasons.length - 1]} &middot; ${list.length} shown &middot; sorted by ${esc(sortName)} ${arrow}
        &middot; <span data-gl="war">WAR</span> (fWAR basis) &middot; <span data-gl="surplus_value">surplus</span> &middot; <span data-gl="p10_p90_bands">P10/P90</span>${pros ? ` &middot; <span data-gl="xfv">eFV</span> &middot; <span data-gl="bust_prob">P(bust)</span>` : ""}</span>
    </div>`;
    // Board tools: the sort picker (CSS shows it once any column has folded,
    // so a folded column stays sortable) and the compare tray once one player
    // is picked, so the first pick has a visible state.
    const pickKeys = viewSortKeys(pros).filter(k => k !== "rank");
    if (!pickKeys.includes(state.sort) && SORT_LBL[state.sort]) pickKeys.push(state.sort);
    const sortPick = `<span class="proj-sort-pick"><label for="proj-sort-sel">Sort</label>
      <select id="proj-sort-sel" class="proj-select">${pickKeys.map(k => `<option value="${k}"${state.sort === k || (state.sort === "rank" && k === "warTotal") ? " selected" : ""}>${esc(SORT_LBL[k])}</option>`).join("")}</select>
      <button type="button" class="chip" id="proj-sort-dir" aria-label="Reverse sort">${arrow} ${dirWord}</button></span>`;
    const cmpOne = state.cmp.length === 1 ? findRow(state.cmp[0]) : null;
    const tray = cmpOne ? `<span class="proj-cmp-tray" role="status">Compare: <strong>${esc(cmpOne.name)}</strong> &middot; pick one more <button type="button" class="chip" data-cmp-clear>clear</button></span>` : "";
    const tools = `<div class="proj-board-tools${pros ? " is-pros" : ""}">${sortPick}${tray}</div>`;
    // Legend chip for the ladder the cells are actually on. Built FROM the ruler,
    // so it cannot drift from the cuts; the reading lives behind the data-gl hook.
    const keyFmt = state.cells === "war" ? (c => String(c)) : RATE_META[state.cells].fmt;
    // The legend has to name the ladder the cells on screen are ACTUALLY on. In
    // the prospect view they are on warProspect and the key was printing the war
    // cuts (6 / 4 / 3 / 2.5 / 1.5) over a pool whose best season is 1.69, so the
    // key disagreed with every cell under it.
    const keyFam = state.cells === "war" ? (pros ? "warProspect" : "war") : state.cells;
    const keyLbl = state.cells === "war" ? (pros ? "WAR heat (ranked in the prospect pool)" : "WAR heat")
                                         : `${RATE_META[state.cells].label} heat`;
    // PA/IP cells carry no tier colour, so they get no key.
    const keyLad = EephusTiers.LADDERS[keyFam];
    const keyTail = keyLad && keyLad.dir === "lo" ? "&gt;" : "&lt;";
    const tierKey = !keyLad ? "" : `<div class="tier-key"><b data-gl="value_ruler">${keyLbl}</b>`
      + keyLad.cuts.map((c, i) => `<span class="tk-${EephusTiers.TIERS[i]}">${keyFmt(c)}</span>`).join("<i>/</i>")
      + `<i>/</i><span class="tk-${EephusTiers.TIERS[5]}">${keyTail}${keyFmt(keyLad.cuts[4])}</span></div>`;
    const table = `<div class="proj-board-wrap"><table class="proj-board-table${pros ? " is-pros" : ""}" data-export data-export-title="MLB Projections">${head}<tbody>${body}</tbody></table>`
      + (body ? "" : pxState("empty", "No players match these filters.")) + `</div>`;
    root.innerHTML = `<div class="fa-board-layout"><div class="fa-board-main proj-board-main">` + boardHead + tierKey + tools + table
      + (list.length > state.limit ? `<div class="proj-more-wrap"><button class="chip" id="proj-more">show ${Math.min(100, list.length - state.limit)} more (${list.length - state.limit} hidden)</button></div>` : "")
      + warMap + `</div>${projBoardSidebar(list)}</div>`;

    const resort = (k, dir, focusSel) => {
      state.sort = k; state.dir = dir;
      syncToURL(); renderTable();
      // The re-render replaced the control; put focus back where the reader was.
      const again = root.querySelector(focusSel);
      if (again && again.focus) again.focus();
    };
    root.querySelectorAll("button[data-psort]").forEach(b => b.onclick = () => {
      const k = b.dataset.psort;
      resort(k, state.sort === k ? -state.dir : naturalDir(k), `button[data-psort="${k}"]`);
    });
    const sel = document.getElementById("proj-sort-sel");
    if (sel) sel.onchange = () => resort(sel.value, naturalDir(sel.value), "#proj-sort-sel");
    const dirBtn = document.getElementById("proj-sort-dir");
    if (dirBtn) dirBtn.onclick = () => resort(state.sort, -state.dir, "#proj-sort-dir");
    // Detail line: toggled in place (no re-render, focus stays put), kept open
    // across sorts and filters through OPEN.
    const toggle = tr => {
      const key = tr.dataset.key;
      const m = findRow(key);
      const btn = tr.querySelector(".proj-xp-btn");
      const next = tr.nextElementSibling;
      if (OPEN.has(key)) {
        OPEN.delete(key);
        if (next && next.classList.contains("proj-detail")) next.remove();
        if (btn) { btn.setAttribute("aria-expanded", "false"); btn.removeAttribute("aria-controls"); }
      } else if (m) {
        OPEN.add(key);
        tr.insertAdjacentHTML("afterend", detailRowHtml(m, pros));
        if (btn) { btn.setAttribute("aria-expanded", "true"); btn.setAttribute("aria-controls", "projd-" + key); }
        if (window.EEPHUS_GL && tr.nextElementSibling) window.EEPHUS_GL.wire(tr.nextElementSibling);
      }
    };
    root.querySelectorAll("tr[data-key]").forEach(tr => {
      const btn = tr.querySelector(".proj-xp-btn");
      if (btn) btn.onclick = () => toggle(tr);
      // A click on a plain part of the row opens the line too; a drag-select
      // does not, so numbers stay copyable.
      tr.onclick = e => {
        if (e.target.closest("a,button,select,input")) return;
        if (window.getSelection && String(window.getSelection())) return;
        toggle(tr);
      };
    });
    ["proj-sx", "proj-sy"].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.onchange = () => {
        state[id === "proj-sx" ? "sx" : "sy"] = el.value;
        syncToURL(); renderTable();
        const d = root.querySelector("details.proj-warmap");
        if (d) d.open = true;
      };
    });
    const more = document.getElementById("proj-more");
    if (more) more.onclick = () => { state.limit += 100; renderTable(); };
    root.querySelectorAll("[data-cmp-key]").forEach(b => b.onclick = () => {
      const k = b.dataset.cmpKey;
      const i = state.cmp.indexOf(k);
      if (i >= 0) state.cmp.splice(i, 1);
      else { state.cmp.push(k); if (state.cmp.length > 2) state.cmp.shift(); }
      syncToURL();
      if (state.cmp.length === 2) { render(); return; }
      renderTable();
      // The re-render replaced the button; keep focus on it, not on <body>.
      const again = root.querySelector(`[data-cmp-key="${cssKey(k)}"]`);
      if (again && again.focus) again.focus();
    });
    const clr = root.querySelector("[data-cmp-clear]");
    if (clr) clr.onclick = () => {
      const was = state.cmp[0];
      state.cmp = []; syncToURL(); renderTable();
      const again = was && root.querySelector(`[data-cmp-key="${cssKey(was)}"]`);
      if (again && again.focus) again.focus();
    };
    fillRowPhotos(root);
    // A payload written before proj_export stamped `fa` (no n_fa) keeps the
    // identity-map fill; a current one paints the chip with the row and the
    // board never fetches player_links.json.
    if (DATA.n_fa == null && window.EEPHUS_HUB) {
      window.EEPHUS_HUB.links().then(L => {
        if (!L) return;
        root.querySelectorAll(".proj-fa-slot[data-fa-key]").forEach(el => {
          const row = (L.byKey || {})[el.dataset.faKey];
          if (row && row.fa) el.innerHTML = faChip({ key: row.key, fa: true });
          el.removeAttribute("data-fa-key");
        });
      });
    }
    if (window.EEPHUS_GL) window.EEPHUS_GL.wire(root);
  }

  // ===========================================================================
  // Head-to-head compare (#cmp=a,b) - two board rows side by side: overlaid
  // projection paths, season-aligned WAR table with the edge per season,
  // value tiles. Works across sources (vet vs prospect compares fine -
  // warAt aligns both to calendar seasons).
  // ===========================================================================
  function faChip(m) {
    return m && m.fa
      ? `<a class="proj-tag proj-fa-chip" href="/fa/#player=${encodeURIComponent(m.key)}" title="In the current FA class: open the market card">$ FA</a>`
      : "";
  }
  function cssKey(k) {
    return (window.CSS && CSS.escape) ? CSS.escape(String(k)) : String(k).replace(/["\\]/g, "\\$&");
  }
  function findRow(key) {
    return (DATA.vets || []).concat(DATA.prospects || []).find(m => m.key === key) || null;
  }
  function renderCompare() {
    const root = document.getElementById("proj-rows");
    const bar = document.getElementById("proj-filters");
    const banner = document.getElementById("proj-banner");
    if (banner) banner.innerHTML = "";
    const a = findRow(state.cmp[0]), b = findRow(state.cmp[1]);
    bar.innerHTML = `<a class="chip" href="#" id="cmp-back">← back to projections</a>
      <button class="chip egfx-chip" id="cmp-gfx" title="Shareable graphic"><span class="egfx-chip-glyph" aria-hidden="true">${window.EephusIco ? window.EephusIco("gfx", 12) : ""}</span>Generate GFX</button>`;
    document.getElementById("cmp-back").onclick = (e) => {
      e.preventDefault(); state.cmp = []; syncToURL(); render();
    };
    if (!a || !b) {
      root.innerHTML = `<div class="state-message">Compare pair not found. <a href="#" onclick="location.hash='';return false;">Back</a>.</div>`;
      return;
    }
    const first = DATA.first_season;
    const seasons = Array.from({ length: DATA.horizon }, (_, t) => first + t);
    const CA = "var(--accent-cyan)", CB = "var(--accent-gold)";
    // overlaid mean paths (bands omitted - two bands over each other is mud;
    // the table below carries the totals band)
    const wA = seasons.map((_, t) => warAt(a, t)), wB = seasons.map((_, t) => warAt(b, t));
    const all = wA.concat(wB).filter(v => v != null);
    const W = 560, H = 180, PX = 36, PY = 16;
    const mn = Math.min(0, ...all), mx = Math.max(1, ...all);
    const x = t => PX + t * (W - PX - 8) / Math.max(1, seasons.length - 1);
    const y = v => PY + (mx - v) * (H - PY - 24) / (mx - mn || 1);
    const line = (w, color) => {
      const pts = w.map((v, t) => v != null ? `${x(t)},${y(v)}` : null).filter(Boolean).join(" ");
      return pts ? `<polyline points="${pts}" fill="none" stroke="${color}" stroke-width="2.5" stroke-linejoin="round"/>` : "";
    };
    const dots = (w, color, nm) => w.map((v, t) => v != null
      ? `<circle cx="${x(t)}" cy="${y(v)}" r="3" fill="${color}"><title>${esc(nm)} ${seasons[t]}: ${fmtWar(v)}</title></circle>` : "").join("");
    const ticks = seasons.map((s, t) => `<text x="${x(t)}" y="${H - 6}" text-anchor="middle" class="mlbp-fan-tick">${s}</text>`).join("");
    const zero = mn < 0 ? `<line x1="${PX}" x2="${W - 8}" y1="${y(0)}" y2="${y(0)}" class="mlbp-fan-zero"/>` : "";
    // The chart drew SEASON ticks only, so both paths were shapes with no
    // magnitude: nothing on it said whether the gap between them was half a win
    // or four. Three WAR labels - axis floor, midpoint, ceiling - in the 36px
    // left gutter the x scale already reserves. Labels only, no gridlines: the
    // one rule on this chart is the dashed zero line, and three more dashes at
    // the same weight would stop it reading as the baseline. One decimal, the
    // precision the table below and every WAR cell on the board use.
    const yTicks = [mx, (mn + mx) / 2, mn].map(v =>
      `<text x="${PX - 6}" y="${y(v) + 3.5}" text-anchor="end" class="mlbp-fan-tick">${v.toFixed(1)}</text>`
    ).join("");
    const chart = `<svg class="mlbp-fan" viewBox="0 0 ${W} ${H}" role="img" aria-label="Projected WAR comparison, ${esc(a.name)} and ${esc(b.name)}, ${seasons[0]} to ${seasons[seasons.length - 1]}, vertical axis ${mn.toFixed(1)} to ${mx.toFixed(1)} WAR, fWAR basis">
      ${yTicks}${zero}${line(wA, CA)}${line(wB, CB)}${dots(wA, CA, a.name)}${dots(wB, CB, b.name)}${ticks}</svg>`;
    // Only the per-side SERIES COLOUR is inline, twice: on the name, and on the
    // stripe the head borrowed from .mlb-card. The ellipsizing box lives on
    // .proj-cmp-name (it finally does, as of 2026-08-04), so the name carries a
    // title.
    //
    // The stripe takes the series colour rather than an org colour on purpose.
    // The payload has no orgColor field at all - measured, 0 of 1,326 veteran
    // rows - so a --org-color stripe here would be a decorative bar claiming an
    // identity it does not carry, and it would be identical on both sides. The
    // series colour is the fact this view actually has: it says which line on
    // the chart below is whose. The photo well is emitted unconditionally and
    // filled by fillRowPhotos, exactly as it is on the board.
    // The club: the mark in the name box is the mouse twin of the code link on
    // the sub line (the name box clips, so the link with the 24 px hit area is
    // the code), the same pair the board row prints. A prospect's club opens
    // his farm system, a veteran's Franchises.
    const cmpCtx = m => (m.src === "prospect" ? "farm" : "franchise");
    const head = (m, color) => `<div class="proj-cmp-head" style="--org-color:${color}">
      ${rowPhoto(m)}
      <span class="proj-cmp-id">
        <strong class="proj-cmp-name" style="color:${color};" title="${esc(m.name)}">${clubA(m.team, teamLogo(m.team), { mark: true, ctx: cmpCtx(m) })}${esc(m.name)}</strong>
        <span class="fa-sub">${esc(m.pos || "")} · ${m.age != null ? Math.floor(m.age) : "?"}${m.team ? ` · ${clubA(m.team, esc(m.team), { ctx: cmpCtx(m) })}` : " · FA"}${tagFor(m)}</span>
      </span></div>`;
    const seasonRows = seasons.map((s, t) => {
      const va = warAt(a, t), vb = warAt(b, t);
      const edge = (va != null && vb != null) ? va - vb : null;
      const cell = (v, m) => v == null
        ? `<td class="proj-dim">${m.src === "prospect" && s < m.eta ? "MiLB" : EM_DASH}</td>`
        : `<td class="proj-war ${EephusTiers.cls(v, warLadder(m))}">${fmtWar(v)}</td>`;
      return `<tr><td>${s}</td>${cell(va, a)}${cell(vb, b)}
        <td class="${edge == null ? "proj-dim" : edge >= 0 ? "proj-pos" : "proj-neg"}">${edge == null ? EM_DASH : (edge >= 0 ? "+" : "") + edge.toFixed(1)}</td></tr>`;
    }).join("");
    const totRow = (label, va, vb, fmt) => {
      const d = (va != null && vb != null) ? va - vb : null;
      return `<tr class="proj-cmp-total"><td>${label}</td><td>${va != null ? fmt(va) : EM_DASH}</td><td>${vb != null ? fmt(vb) : EM_DASH}</td>
        <td class="${d == null ? "proj-dim" : d >= 0 ? "proj-pos" : "proj-neg"}">${d == null ? EM_DASH : (d >= 0 ? "+" : "") + (fmt === fmtWar ? d.toFixed(1) : money(d))}</td></tr>`;
    };
    // The newsprint eyebrow the board and the FA class board open with, in place
    // of .mlbp-section-title - that is the PLAYER PAGE's section dialect, and
    // this view is a board view reached from the board.
    root.innerHTML = `<div class="mlbp-page">
      <div class="mlbp-section proj-cmp-section">
        <div class="newsprint-eyebrow">
          <span class="newsprint-eyebrow-label">Head-to-Head</span>
          <span class="newsprint-eyebrow-meta">projected mean WAR (fWAR basis), season-aligned ${seasons[0]}-${seasons[seasons.length - 1]}${(a.src === "prospect" || b.src === "prospect") ? " &middot; prospects join at their PROSPX ETA" : ""}</span>
        </div>
        <div class="proj-cmp-heads">${head(a, CA)}${head(b, CB)}</div>
        ${chart}
        <table class="detail-table proj-table proj-cmp-table">
          <thead><tr><th>Season</th><th style="color:${CA};">${esc(a.name)}</th><th style="color:${CB};">${esc(b.name)}</th><th>Edge</th></tr></thead>
          <tbody>${seasonRows}
            ${totRow(`${DATA.horizon}y WAR`, warShown(a), warShown(b), fmtWar)}
            ${totRow("Surplus", surOf(a), surOf(b), money)}</tbody></table>
        <div class="fa-note proj-cmp-note">Edge = left minus right. <span data-gl="surplus_value">Surplus</span> is club control window surplus for a veteran, unsigned seasons priced through ${seasons[seasons.length - 1]} at most and a longer guarantee through its last season, and projected surplus over his controlled seasons for a prospect: both value above cost, not like-for-like terms.</div>
      </div></div>`;
    const gfx = document.getElementById("cmp-gfx");
    if (gfx) gfx.onclick = () => {
      if (!window.EEPHUS_HUB) return;
      // Declarative since GFX slice 4: the "compare" template owns the
      // no-tiles / two-column layout; this site only supplies the columns.
      window.EEPHUS_HUB.openCard({
        template: "compare",
        data: { columns: [
          { title: esc(a.name), rows: seasons.map((s, t) => [String(s), fmtWar(warAt(a, t))]) },
          { title: esc(b.name), rows: seasons.map((s, t) => [String(s), fmtWar(warAt(b, t))]) },
        ] },
        module: "MLB Projections",
        accentToken: "--accent-cyan",
        name: `${a.name} vs ${b.name}`,
        meta: `head-to-head · projected ${DATA.horizon}y WAR (fWAR basis) ${fmtWar(warShown(a))} vs ${fmtWar(warShown(b))}`,
        url: "eephus.io/projections",
        filename: `eephus-cmp-${a.key}-${b.key}.png`,
        caption: "eephus projection engine (proj_lgbm_v1) · season-aligned mean WAR, trained on published fWAR",
      });
    };
    // Same async well fill the board rows use, so a compare opened on two
    // prospect rows (which carry no mlbam in the payload) still gets faces.
    fillRowPhotos(root);
    if (window.EEPHUS_GL) window.EEPHUS_GL.wire(root);
  }

  // ===========================================================================
  // MLB player page (#player={key}) - the per-player detail surface
  // (data/mlb_player_detail.json, mlb_player_export.py). A hero of at most
  // four tiles, then tabs by question: Overview, Hitting, Pitching, Defense,
  // Value, Projection & Contract, Scouting, Discussion (mlbpTabs). The open
  // tab is state (#ptab=); async fills patch stable slots (slotHTML).
  // ===========================================================================
  // The player page's own headshotURL is GONE (2026-08-05). It duplicated the
  // board builder and lost the two things that builder had learned: it asked
  // for `d_people:generic`, which serves a silhouette at HTTP 200 so no onerror
  // in the degrade chain can ever fire, and it never consulted photo_ctx, so
  // every milb-only prospect on this surface got that silhouette instead of the
  // photo that exists one context over. Both hero boxes now call the shared
  // `headshotURL` at the top of this file with the box they actually render.
  function pctClass(p) {
    return p >= 80 ? "is-elite" : p >= 60 ? "is-good" : p >= 40 ? "is-avg" : p >= 20 ? "is-low" : "is-poor";
  }

  // ---- scale families --------------------------------------------------------
  // One ruler per family, never shared, and every CUT now lives in
  // assets/eephus-tiers.js: "z" is 100 + 10z (WAR/PA+, WAR/IP+, DEM+), "ratio" is
  // the HEM+ family at wRC+ width, "run" is REM+/SEM+/RIV+. A 113 is `good` on
  // the ratio ruler and `great` on the z ruler, so DEM+ never borrows the HEM+
  // cut. The family class (vt-fam-z against vt-fam-ratio) rides on every banded
  // value so a test can read WHICH ruler drew it.
  //
  // The two card families that used to disagree with the /mlbstats/ board are
  // fixed by deletion here: "ratio" was an 88 / 112 proj-pos / proj-neg SIGN pair
  // with no elite step, and "run" banded 95 / 105, neither of which is what the
  // board paints for the same number. Both take the board ladder now.
  //
  // Only the LAYOUT hook stays local. The shaded guide band on the dot ruler is
  // the family's own neutral zone, read off the ladder (avg cut to good cut), so
  // no threshold is typed twice.
  const SCALE_HOOK = { ratio: "mlbp-scale-ratio", run: "mlbp-scale-ratio", z: "mlbp-scale-z" };
  function bandCls(v, fam) {
    const hook = SCALE_HOOK[fam];
    if (!hook) return "";
    const c = EephusTiers.clsInk(v, fam);
    return c ? hook + " " + c : hook;
  }
  // Glossary hook: the explanation lives in the glossary entry, not on the page.
  const term = (slug, label) => (slug ? `<span data-gl="${slug}">${label}</span>` : label);
  // Signed runs and WPA: "+1.2", "-0.4", "0.0" (never "-0.0").
  function signed(v, d) {
    const n = Number(v);
    if (v == null || v === "" || !Number.isFinite(n)) return EM_DASH;
    const r = Number(n.toFixed(d));
    return r === 0 ? (0).toFixed(d) : (r > 0 ? "+" : "") + r.toFixed(d);
  }
  const fmtInn = v => (v == null ? EM_DASH : Number(v).toFixed(1).replace(/\.0$/, ""));
  function tileHTML(label, val, cls, opt) {
    const o = opt || {};
    return `<div class="mlbp-tile"><span class="mlbp-tile-label">${term(o.gl, label)}</span>`
      + `<span class="mlbp-tile-val ${cls || ""}">${val}</span>`
      + (o.sub ? `<span class="mlbp-tile-sub">${o.sub}</span>` : "") + `</div>`;
  }
  // Every section carries a stable data-mlbp-section id: the smoke test isolates
  // sections by it, never by markup that a styling change would move.
  function section(id, title, sub, body) {
    if (!body) return "";
    return `<div class="mlbp-section" data-mlbp-section="${id}"><div class="mlbp-section-title">${title}${sub ? ` <span class="fa-sub">${sub}</span>` : ""}</div>${body}</div>`;
  }

  // ---- async slots -----------------------------------------------------------
  // Each async fill lands in a stable wrapper instead of re-rendering the page,
  // so the open tab, the scroll position and a mounted Discussion thread survive
  // it. The wrapper is always emitted (empty until its data lands). When the
  // wrapper is missing, because its tab had nothing to show at first paint,
  // the fill falls back to one full render.
  const slotId = name => "mlbp-slot-" + name;
  function slotHTML(name, html) {
    return `<div class="mlbp-slot" id="${slotId(name)}" data-mlbp-slot="${name}">${html || ""}</div>`;
  }
  function patchSlot(name, key, html) {
    if (!key || state.player !== key) return;
    const el = document.getElementById(slotId(name));
    if (el) {
      el.innerHTML = html || "";
      if (window.EEPHUS_GL) window.EEPHUS_GL.wire(el);
    } else if (html) {
      renderPlayer(key);
    }
  }
  const currentCard = () => (state.player && DETAIL && (DETAIL.players || {})[state.player]) || null;

  // ---- shared visual components ----------------------------------------------
  // Savant percentile rows. Luck (xwOBA minus wOBA) is not a skill percentile:
  // painted on the percentile colours, the hitter whose contact ran furthest
  // ahead of his results reads as elite, so it keeps its number on a neutral chip.
  // Colour (owner ask 2026-10-01): one colour per bar and chip from the shared
  // percentile gradient (EephusTiers.pctColor), carried inline as --pct so the
  // stylesheet paints the fill and the chip from it; the pctClass step stays on
  // both as the fallback a browser without color-mix paints instead.
  // The pools mlb_player_export pulls: the contact leaderboard at 25+ batted
  // balls, the expected-stats leaderboard with no floor. Neither is a
  // qualified pool.
  const SAVANT_POOL = "vs Savant leaderboards (contact: 25+ batted balls; expected stats: no floor)";
  function sliders(sc, sid) {
    if (!sc || !sc.metrics || !sc.metrics.length) return "";
    const isLuck = m => /^luck/i.test(String(m.label || ""));
    const rows = sc.metrics.filter(m => !isLuck(m)).map(m => {
      const c = EephusTiers.pctColor(m.pct);
      const v = c ? `--pct:${c};` : "";
      return `
      <div class="mlbp-slider">
        <span class="mlbp-slider-label">${esc(m.label)}</span>
        <div class="mlbp-slider-track"><div class="mlbp-slider-fill ${pctClass(m.pct)}" style="${v}width:${m.pct}%;"></div>
          <span class="mlbp-slider-pct ${pctClass(m.pct)}" style="${v}left:${Math.min(94, Math.max(2, m.pct))}%;">${m.pct}</span></div>
        <span class="mlbp-slider-val">${esc(m.value)}</span>
      </div>`;
    }).join("");
    const luck = sc.metrics.find(isLuck);
    const luckHTML = luck
      ? `<div class="mlbp-luck"><span class="mlbp-luck-label">${esc(luck.label)}</span><span class="mlbp-luck-val">${esc(luck.value)}</span></div>` : "";
    return section(sid, "Statcast Percentiles", `${esc(String(sc.season))} · ${SAVANT_POOL}`, rows + luckHTML);
  }
  // Dot ruler for one scale family: every index on it shares the axis, the
  // centre line is 100 and the shaded band is the family's neutral zone.
  function rulerHTML(rows, fam, axis) {
    const lad = EephusTiers.LADDERS[fam];
    const use = (rows || []).filter(r => r && r.v != null && Number.isFinite(Number(r.v)));
    if (!SCALE_HOOK[fam] || !lad || !use.length) return "";
    // The shaded band is the family's neutral zone: its `avg` floor up to its
    // `good` floor, read off the ladder rather than typed.
    const s = { lo: lad.cuts[4], hi: lad.cuts[2] };
    // The axis widens in steps of 10 to hold every value on it, so a 171 is
    // drawn at 171 rather than pinned to the edge.
    const vals = use.map(r => Number(r.v));
    const a0 = Math.min((axis || [60, 160])[0], Math.floor(Math.min(...vals) / 10) * 10);
    const a1 = Math.max((axis || [60, 160])[1], Math.ceil(Math.max(...vals) / 10) * 10);
    const at = v =>Math.max(0, Math.min(100, (Number(v) - a0) / (a1 - a0) * 100));
    const guide = `<span class="mlbp-ruler-band" style="left:${at(s.lo).toFixed(1)}%;width:${(at(s.hi) - at(s.lo)).toFixed(1)}%;"></span>`
      + `<span class="mlbp-ruler-mid" style="left:${at(100).toFixed(1)}%;"></span>`;
    const body = use.map(r => {
      const cls = bandCls(r.v, fam);
      // The DOT carries the layout hook only. `.mlbp-ruler-dot` sets its own
      // `color` at 0,1,0 AFTER the ruler block, so a tier class on the dot loses
      // on source order and paints nothing: it was a live class with no effect
      // (the old rem-* classes were equally inert there). The tier rides the
      // VALUE beside it, which is the element the reader reads.
      return `<div class="mlbp-ruler-row"><span class="mlbp-ruler-label">${term(r.gl, r.label)}</span>`
        + `<div class="mlbp-ruler-track">${guide}<span class="mlbp-ruler-dot ${SCALE_HOOK[fam]}" style="left:${at(r.v).toFixed(1)}%;"></span></div>`
        + `<span class="mlbp-ruler-val ${cls}">${esc(String(r.v))}${r.note ? `<span class="fa-band"> ${esc(r.note)}</span>` : ""}</span></div>`;
    }).join("");
    const scale = [a0, 100, a1].map(t => `<span style="left:${at(t).toFixed(1)}%;">${t}</span>`).join("");
    return `<div class="mlbp-ruler">${body}<div class="mlbp-ruler-row mlbp-ruler-axis"><span></span><div class="mlbp-ruler-scale">${scale}</div><span></span></div></div>`;
  }
  // Horizontal run bars diverging about zero (defensive runs). `neutral` rows
  // (the positional ladder) are context, not a grade, so they carry no tone.
  function runBars(rows) {
    const use = (rows || []).filter(r => r && r.v != null && Number.isFinite(Number(r.v)));
    if (!use.length) return "";
    const m = Math.max(10, ...use.map(r => Math.abs(Number(r.v))));
    return `<div class="mlbp-runbars">${use.map(r => {
      const v = Number(r.v), w = Math.abs(v) / m * 50;
      const left = v >= 0 ? 50 : 50 - w;
      const tone = r.neutral ? "" : v > 0 ? "proj-pos" : v < 0 ? "proj-neg" : "";
      return `<div class="mlbp-runbar${r.total ? " is-total" : ""}${r.sub ? " is-sub" : ""}">`
        + `<span class="mlbp-runbar-label">${term(r.gl, r.label)}</span>`
        + `<div class="mlbp-runbar-track"><span class="mlbp-runbar-zero"></span><span class="mlbp-runbar-fill ${tone}" style="left:${left.toFixed(1)}%;width:${w.toFixed(1)}%;"></span></div>`
        + `<span class="mlbp-runbar-val ${tone}">${signed(v, 1)}</span></div>`;
    }).join("")}</div>`;
  }
  // WAR by season on the served frame. `a` is the card's primary side (hitting,
  // or pitching for a pitcher), `b` the pitching side of a two-way card; `refA`
  // and `refB` are the bWAR inputs where they differ at 1dp (absent = equal);
  // `fgA` and `fgB` are FanGraphs' published WAR, a reference only (absent = no
  // published value), shown in the bar's tooltip and never drawn or summed into
  // the eWAR bar.
  function warSeasons(p) {
    const by = {};
    const add = (rows, side) => (rows || []).forEach(r => {
      if (!r || r.war == null) return;
      const c = by[r.y] || (by[r.y] = { y: r.y, a: null, b: null, refA: null, refB: null, fgA: null, fgB: null });
      c[side] = r.war;
      if (r.war_bwar != null) c[side === "a" ? "refA" : "refB"] = r.war_bwar;
      if (r.war_fwar != null) c[side === "a" ? "fgA" : "fgB"] = r.war_fwar;
    });
    add(p.career, "a");
    if (p.twoWay) add(p.careerPit, "b");
    return Object.values(by).sort((x, y) => x.y - y.y);
  }
  const warTot = s => (s.a || 0) + (s.b || 0);
  const warRef = s => ((s.refA == null && s.refB == null) ? null
    : (s.refA != null ? s.refA : (s.a || 0)) + (s.refB != null ? s.refB : (s.b || 0)));
  // FanGraphs' published WAR for the season, only when every side the bar
  // carries has a published value (a partial sum would mix in eWAR).
  const warFg = s => (((s.a != null && s.fgA == null) || (s.b != null && s.fgB == null)
    || (s.fgA == null && s.fgB == null)) ? null : (s.fgA || 0) + (s.fgB || 0));
  const FG_WAR_TIP = "FanGraphs' published WAR, as MLB's StatsAPI publishes it. A reference only: the site's WAR is eWAR.";
  const REAL_WAR_TIP = "eWAR realized: the same frame as eWAR, with pitchers priced on the runs they allowed, adjusted for park, defense and inherited runners. Shown beside eWAR; it never sorts, sums or ranks.";
  const V2_WAR_TIP = "eWAR v2, the site's earlier WAR: Baseball-Reference's WAR with pitching re-priced on FIP. A reference only.";
  const BREF_WAR_TIP = "Baseball-Reference's WAR (bWAR). A reference only.";
  function warBarsSVG(ss, sides) {
    const use = (ss || []).filter(s => s.a != null || s.b != null);
    if (!use.length) return "";
    const W = 560, H = 180, PL = 8, PR = 8, PT = 18, PB = 22;
    const pos = s => Math.max(0, s.a || 0) + Math.max(0, s.b || 0);
    const neg = s => Math.min(0, s.a || 0) + Math.min(0, s.b || 0);
    const mx = Math.max(1, ...use.map(pos), ...use.map(s => warRef(s) || 0));
    const mn = Math.min(0, ...use.map(neg), ...use.map(s => warRef(s) || 0));
    const slot = (W - PL - PR) / use.length, bw = Math.min(34, slot * 0.62);
    const y = v => PT + (mx - v) * (H - PT - PB) / ((mx - mn) || 1);
    const cx = i => PL + slot * (i + 0.5);
    const bars = use.map((s, i) => {
      const r = warRef(s);
      const title = `${s.y}: ${fmtWar(warTot(s))} eWAR`
        + (sides && s.b != null ? ` (${sides[0]} ${fmtWar(s.a)}, ${sides[1]} ${fmtWar(s.b)})` : "")
        + (r != null ? `, bWAR ${fmtWar(r)}` : "")
        + (warFg(s) != null ? `, FanGraphs WAR ${fmtWar(warFg(s))} (reference)` : "");
      let pb = 0, nb = 0, out = "";
      [["a", s.a], ["b", s.b]].forEach(([k, v]) => {
        if (v == null) return;
        const lo = v >= 0 ? pb : nb + v, hi = v >= 0 ? pb + v : nb;
        if (v >= 0) pb += v; else nb += v;
        out += `<rect x="${(cx(i) - bw / 2).toFixed(1)}" y="${y(hi).toFixed(1)}" width="${bw.toFixed(1)}" height="${Math.max(0.5, y(lo) - y(hi)).toFixed(1)}" class="mlbp-warbar${k === "b" ? " mlbp-warbar-b" : ""}"><title>${esc(title)}</title></rect>`;
      });
      if (r != null)
        out += `<line x1="${(cx(i) - bw / 2 - 3).toFixed(1)}" x2="${(cx(i) + bw / 2 + 3).toFixed(1)}" y1="${y(r).toFixed(1)}" y2="${y(r).toFixed(1)}" class="mlbp-warbar-ref"><title>${s.y}: bWAR ${fmtWar(r)}</title></line>`;
      const ly = warTot(s) >= 0 ? y(pb) - 4 : y(nb) + 11;
      out += `<text x="${cx(i).toFixed(1)}" y="${ly.toFixed(1)}" text-anchor="middle" class="mlbp-warbar-val">${fmtWar(warTot(s))}</text>`
        + `<text x="${cx(i).toFixed(1)}" y="${H - 6}" text-anchor="middle" class="mlbp-fan-tick">${s.y}</text>`;
      return out;
    }).join("");
    return `<svg class="mlbp-fan mlbp-warbars" viewBox="0 0 ${W} ${H}" role="img" aria-label="eWAR by season">`
      + `<line x1="${PL}" x2="${W - PR}" y1="${y(0).toFixed(1)}" y2="${y(0).toFixed(1)}" class="mlbp-warbar-zero"/>${bars}</svg>`;
  }

  // ---- projection ------------------------------------------------------------
  function fanChart(p) {
    const war = (p.proj && p.proj.war) || [];
    if (war.length < 2) return "";
    const lo = (p.proj && p.proj.warP10) || [], hi = (p.proj && p.proj.warP90) || [];
    const first = DATA.first_season, W = 560, H = 170, PX = 36, PY = 16;
    const all = war.concat(lo, hi).filter(v => v != null);
    const mn = Math.min(0, ...all), mx = Math.max(1, ...all);
    const x = t => PX + t * (W - PX - 8) / (war.length - 1);
    const y = v => PY + (mx - v) * (H - PY - 24) / (mx - mn || 1);
    const pts = a => a.map((v, t) => `${x(t)},${y(v)}`).join(" ");
    const band = (lo.length && hi.length)
      ? `<polygon points="${pts(hi)} ${lo.map((v, t) => `${x(lo.length - 1 - t)},${y(lo[lo.length - 1 - t])}`).join(" ")}" class="mlbp-fan-band"/>` : "";
    const ticks = war.map((v, t) => `<text x="${x(t)}" y="${H - 6}" text-anchor="middle" class="mlbp-fan-tick">${first + t}</text>`).join("");
    const zero = (mn < 0) ? `<line x1="${PX}" x2="${W - 8}" y1="${y(0)}" y2="${y(0)}" class="mlbp-fan-zero"/>` : "";
    return section("projection-fan", "Projected WAR", "mean, P10-P90 · expected path, the surplus basis · fWAR basis",
      `<svg class="mlbp-fan" viewBox="0 0 ${W} ${H}" role="img" aria-label="Projected WAR path">${band}
        <polyline points="${pts(war)}" class="mlbp-fan-line"/>
        ${war.map((v, t) => `<circle cx="${x(t)}" cy="${y(v)}" r="3" class="mlbp-fan-dot"><title>${first + t}: ${fmtWar(v)}${lo[t] != null ? ` (${fmtWar(lo[t])}-${fmtWar(hi[t])})` : ""}</title></circle>`).join("")}
        ${zero}${ticks}</svg>`);
  }
  // Explicit upside read-out: the per-year P90 (ceiling) path, each season
  // labeled on its own. Per-year quantiles are NOT additive, so this element
  // never shows a multi-year P90 total (the sum of per-year P90s is not the
  // P90 of the total; see the F-01 ledger note).
  function upsidePath(p) {
    const hi = (p.proj && p.proj.warP90) || [];
    if (!hi.length || !hi.some(v => v != null)) return "";
    const first = DATA.first_season;
    const cells = hi.map((v, t) => `<div class="mlbp-cell"><span class="mlbp-cell-label">${first + t}</span><span class="mlbp-cell-val ${EephusTiers.clsInk(v, "war")}">${fmtWar(v)}</span></div>`).join("");
    return section("upside", "Upside", "P90 outcome per season · per-year percentiles; they do not add up to a multi-year total",
      `<div class="mlbp-grid mlbp-grid-flow">${cells}</div>`);
  }
  function faBlock(p) {
    const f = p.fa;
    if (!f) return "";
    const verd = f.verdict ? `<span class="mlbp-tile-chip">${esc(f.verdict)}</span>` : "";
    const cells = [
      ["Projected", f.projYears != null ? `${f.projYears}y / ${money(f.projGuar)}` : EM_DASH],
      ["Proj AAV", f.projAav != null ? `${money(f.projAav)}${f.projAavP10 != null ? ` <span class="fa-band">(${money(f.projAavP10)}-${money(f.projAavP90)})</span>` : ""}` : EM_DASH],
      ["Rational value", f.rational != null ? money(f.rational) : EM_DASH],
      ["Contract surplus", f.surplus != null ? money(f.surplus) : EM_DASH],
      ["Deal+", f.dealPlus != null ? String(Math.round(f.dealPlus)) : EM_DASH],
      ["Prior AAV", f.prevAav != null ? money(f.prevAav) : EM_DASH],
    ];
    return section("contract-fa", "Free Agency", `${esc(f.status || "")} · ${term("fa_gates", "Gate 2")} market model ${verd}`,
      `<div class="mlbp-grid">${cells.map(([l, v]) => `<div class="mlbp-cell"><span class="mlbp-cell-label">${l}</span><span class="mlbp-cell-val">${v}</span></div>`).join("")}</div>
      ${faPricingPathNote(p)}
      <div class="fa-sub mlbp-block-foot"><a class="fa-player-link" href="/fa/#player=${encodeURIComponent(p.key)}">FA market card &rarr;</a></div>`);
  }
  // TWO PATHS, SAID ONCE (M05-06, 2026-09-25). The expected path above is
  // proj_lgbm_v1; the FA numbers in this block (Rational value, Contract
  // surplus, Deal+) are priced on the Marcel champion path, the input the FA
  // market model was gated on (fa_export use_ml=False, a do-not-reopen item).
  // The block names the path it prices and its per-season values, so a reader
  // moving between this card and /fa/ sees why the two pages print different
  // WAR for the same season instead of finding a contradiction.
  function faPricingPathNote(p) {
    const f = p.fa || {}, pr = p.proj || {};
    const fp = f.warPath || [];
    if (!fp.length) return "";
    const first = DATA ? DATA.first_season : null;
    const ml = pr.war || [];
    const n = Math.min(fp.length, ml.length);
    const sum = (a, k) => a.slice(0, k).reduce((s, v) => s + (v || 0), 0);
    const cmp = n && first != null
      ? ` Over ${first}-${first + n - 1} the FA path sums ${fmtWar(sum(fp, n))} against ${fmtWar(sum(ml, n))} on the projection path above.`
      : "";
    return `<div class="fa-sub mlbp-block-foot" data-fa-pricing-path>FA values are priced on the ${term("fa_projection_engine", "Marcel champion path")}, not the projection path above: ${fp.map(fmtWar).join(" / ")}${first != null ? ` (${first}-${first + fp.length - 1})` : ""}, Deal WAR ${fmtWar(f.warTotal)}.${cmp}${faGateClause()}</div>`;
  }
  // EACH SURFACE SERVES THE ENGINE THAT WON ITS OWN GATE (owner answer M15-1,
  // 2026-09-25). Both sentences read accountability.surface_engines, which
  // proj_export copies out of the two committed eval artifacts, so the verdict
  // each prints is the measured one and an absent block prints nothing. The
  // markup is literal, not term(): the fold calls these from render().
  function surfaceEngines() {
    return ((DATA && DATA.accountability) || {}).surface_engines || {};
  }
  function measuredOn(when) {
    return when ? `, measured ${esc(String(when).slice(0, 10))}` : "";
  }
  // A gate row that is pending re-measure says so beside its figures.
  function pendingNote(x) {
    return x && x.remeasure_pending ? ` Its registry row: ${esc(x.remeasure_pending)}.` : "";
  }
  function projGateSentence() {
    const p = surfaceEngines().projections;
    const rows = ((p && p.by_horizon) || []).filter(r => r.mae != null && r.mae_comparator != null);
    if (!rows.length) return "";
    const ahead = rows.filter(r => r.mae < r.mae_comparator).length;
    const h1 = rows[0];
    const where = ahead === rows.length ? "at every scored horizon" : `at ${ahead} of ${rows.length} scored horizons`;
    return ` ${esc(p.engine)} serves here: it is ahead of ${esc(p.comparator)} ${where} of the ${esc(p.frame)} (year ${h1.h} MAE ${h1.mae.toFixed(3)} against ${h1.mae_comparator.toFixed(3)}${measuredOn(p.generated_at)}).${pendingNote(p)}`;
  }
  function faGateClause() {
    const f = surfaceEngines().fa;
    const g = f && f.pooled && f.pooled.guarantee;
    if (!g || g.mae_model == null || g.mae_base == null) return "";
    const verdict = f.pass ? "passed" : "is failing";
    return ` /fa/ keeps the champion path, the input its market model ${verdict} <span data-gl="fa_gates">Gate 2</span> on (guarantee MAE $${g.mae_model.toFixed(2)}M against $${g.mae_base.toFixed(2)}M for its baseline, n ${String(Math.round(Number(g.n))).replace(/\B(?=(\d{3})+(?!\d))/g, ",")}${measuredOn(f.generated_at)}).${pendingNote(f)}`;
  }
  // ---- projected components (PJ_7, class 2, dark) ---------------------------
  // proj_export writes the component lines behind PROJ_COMPONENTS_LIVE and
  // mlb_player_export copies them into the card shard as proj.comp. Absent,
  // componentBlock returns "" and the tab is what it was. The lines sit on
  // FanGraphs' WAR frame while the realized seasons are eWAR, so the frame line
  // says which is which. Each runs or WAR cell carries its own 80% range (P10
  // to P90) in its title and aria-label where the block publishes one; no
  // range is ever built by adding component ranges, and the served WAR row
  // keeps the WAR head's own warP10 / warP90. A head its own PJ-C component
  // test did not pass is null in every block and named in notServed (PJ_8):
  // it prints "not projected" and the foot note says so once for all players.
  const COMP_NP = "not projected";
  const COMP_NP_NAMES = { bsr: "baserunning runs", fld: "fielding runs", pos: "positional runs",
                          gmli: "reliever gmLI", ra9_gap: "the RA9 adjustment", war_fip: "FIP-based WAR",
                          pa: "playing time (PA)", ip: "playing time (IP)" };
  const compInt = v => String(Math.round(v));
  const compPct = v => formatMetric(v * 100, "pct");
  const compRuns = v => signed(v, 1);
  // A range read for one season: "80% range a to b runs", or "" where the block
  // publishes no range for that season. A playing-time floor is zero.
  function compRange(lo, hi, fmt, unit, opt) {
    const o = opt || {};
    return t => {
      const a = lo ? lo[t] : null, b = hi ? hi[t] : null;
      if (a == null || b == null) return "";
      return `${o.lead ? o.lead(t) : ""}${o.name || "80% range"} ${fmt(o.floor0 ? Math.max(0, a) : a)} to ${fmt(b)}${unit}`;
    };
  }
  // One row: the label, then one cell per season. A run of null seasons prints
  // once, across those seasons, as "not projected".
  function compRow(id, label, plain, vals, fmt, seasons, rng) {
    const n = seasons.length;
    const at = t => (vals ? (vals[t] ?? null) : null);
    let cells = "", t = 0;
    while (t < n) {
      if (at(t) == null) {
        let k = t;
        while (k < n && at(k) == null) k++;
        const when = k - t > 1 ? `${seasons[t]}-${seasons[k - 1]}` : String(seasons[t]);
        cells += `<td${k - t > 1 ? ` colspan="${k - t}"` : ""} class="fa-dim" style="text-align:center" aria-label="${esc(`${when} ${plain}: ${COMP_NP}`)}">${COMP_NP}</td>`;
        t = k;
        continue;
      }
      const txt = fmt(at(t));
      const tip = rng ? rng(t) : "";
      cells += `<td style="text-align:center"${tip ? ` title="${esc(tip)}"` : ""} aria-label="${esc(`${seasons[t]} ${plain}: ${txt}${tip ? `, ${tip}` : ""}`)}">${txt}</td>`;
      t++;
    }
    return `<tr data-proj-comp-row="${id}"><th scope="row">${label}</th>${cells}</tr>`;
  }
  function componentBlock(p) {
    const pr = p.proj || {};
    const c = pr.comp;
    if (!c || (!c.hit && !c.pit)) return "";
    const H = c.hit, P = c.pit;
    const base = c.base != null ? c.base : (DATA ? DATA.first_season : null);
    const n = (c.warComp || pr.war || []).length || (DATA && DATA.horizon) || 5;
    const seasons = Array.from({ length: n }, (_, t) => base + t);
    const grp = label => `<tr data-proj-comp-group><th scope="colgroup" colspan="${n + 1}">${label}</th></tr>`;
    const runs = (lo, hi, opt) => compRange(lo, hi, compRuns, " runs", opt);
    const rows = [];
    if (H) {
      const lo = H.p10 || {}, hi = H.p90 || {};
      const fp = { name: "80% range of fielding plus positional runs together" };
      rows.push(grp("Hitting"),
        compRow("pa", term("projected_playing_time", "PA"), "PA", H.pa, compInt, seasons, compRange(lo.pa, hi.pa, compInt, " PA", { floor0: true })),
        compRow("k", term("k_pct", "K%"), "K%", H.k, compPct, seasons),
        compRow("bb", term("bb_pct", "BB%"), "BB%", H.bb, compPct, seasons),
        compRow("iso", term("iso", "ISO"), "ISO", H.iso, rate3, seasons),
        compRow("babip", term("babip", "BABIP"), "BABIP", H.babip, rate3, seasons),
        compRow("woba", term("woba", "wOBA"), "wOBA", H.woba, rate3, seasons),
        compRow("wrc", term("wrc_plus", "wRC+"), "wRC+", H.wrc, compInt, seasons),
        compRow("bat", term("projected_component_runs", "Batting runs"), "Batting runs", H.bat, compRuns, seasons, runs(lo.bat, hi.bat)),
        compRow("bsr", term("projected_component_runs", "Baserunning runs"), "Baserunning runs", H.bsr, compRuns, seasons, runs(lo.bsr, hi.bsr)),
        compRow("fld", term("projected_component_runs", "Fielding runs"), "Fielding runs", H.fld, compRuns, seasons, runs(lo.fldPos, hi.fldPos, fp)),
        compRow("pos", term("projected_component_runs", "Positional runs"), "Positional runs", H.pos, compRuns, seasons, runs(lo.fldPos, hi.fldPos, fp)),
        compRow("lg", term("projected_component_runs", "League runs"), "League runs", H.lg, compRuns, seasons, runs(lo.lg, hi.lg)),
        compRow("rep", term("projected_component_runs", "Replacement runs"), "Replacement runs", H.rep, compRuns, seasons, runs(lo.rep, hi.rep)));
      if (P) rows.push(compRow("war-hit", term("war_from_components", "Hitting WAR from components"), "Hitting WAR from components", H.warComp, fmtWar, seasons));
    }
    if (P) {
      const lo = P.p10 || {}, hi = P.p90 || {};
      const ra9 = runs(lo.ra9Gap, hi.ra9Gap, {
        lead: t => (P.ra9Gap && P.ra9Gap[t] != null ? `RA9 adjustment ${compRuns(P.ra9Gap[t])} runs; its ` : "RA9 adjustment "),
      });
      rows.push(grp("Pitching"),
        compRow("ip", term("projected_playing_time", "IP"), "IP", P.ip, compInt, seasons, compRange(lo.ip, hi.ip, compInt, " IP", { floor0: true })),
        compRow("k-pit", term("k_pct_pitcher", "K%"), "K%", P.k, compPct, seasons),
        compRow("bb-pit", term("bb_pct_pitcher", "BB%"), "BB%", P.bb, compPct, seasons),
        compRow("hr9", "HR/9", "HR/9", P.hr9, v => Number(v).toFixed(2), seasons),
        compRow("fip", term("fip", "FIP"), "FIP", P.fip, v => Number(v).toFixed(2), seasons),
        compRow("war-fip", term("fip_based_war", "FIP-based WAR"), "FIP-based WAR", P.warFip, fmtWar, seasons),
        // PJ-Q3 (owner answer 2026-10-01): both lines, FIP first.
        compRow("war-ra9", term("ra9_based_war", "RA9-based WAR"), "RA9-based WAR", P.warRa9, fmtWar, seasons, ra9));
    }
    rows.push(grp(H && P ? "WAR, both sides" : "WAR"),
      compRow("war-comp", term("war_from_components", "WAR from components"), "WAR from components", c.warComp, fmtWar, seasons),
      compRow("gap", term("projection_gap", "Rest of the served projection"), "Rest of the served projection", c.gap, v => signed(v, 1), seasons),
      compRow("war", term("war", "Served WAR"), "Served WAR", pr.war, fmtWar, seasons, compRange(pr.warP10, pr.warP90, fmtWar, " WAR")));
    const where = H && P ? "the Hitting and Pitching tabs" : H ? "the Hitting tab" : "the Pitching tab";
    const npName = k => COMP_NP_NAMES[k] || String(k).replace(/_/g, " ");
    const ns = [...((H && H.notServed) || []), ...((P && P.notServed) || [])];
    const np = [...((H && H.notProjected) || []), ...((P && P.notProjected) || [])]
      .filter(k => !ns.includes(k)).map(npName);
    const nsNames = [...new Set(ns.map(npName))];
    const nsNote = nsNames.length
      ? ` Not projected for any player: ${esc(nsNames.join(", "))}, each held back by its own component test; any runs they carry sit in the rest of the served projection.` : "";
    const npNote = (np.length
      ? ` Not projected for him: ${esc([...new Set(np)].join(", "))}; those runs sit in the rest of the served projection.` : "") + nsNote;
    const head = `<thead><tr><th scope="col">Component</th>${seasons.map(s => `<th scope="col">${s}</th>`).join("")}</tr></thead>`;
    return section("projection-components", "Projected components", "means per season · FanGraphs frame",
      `<div class="fa-sub mlbp-block-foot" data-proj-comp-frame>Components on FanGraphs' WAR frame; the season history on ${where} shows ${term("ewar", "eWAR")}.</div>`
      + `<div class="mlbp-table-wrap"><table class="detail-table" data-proj-comp-table>${head}<tbody>${rows.join("")}</tbody></table></div>`
      + `<div class="fa-sub mlbp-block-foot">Each row is rounded on its own; before rounding, WAR from components plus the rest of the served projection equals the served WAR. Hover a cell for its 80% range where the line publishes one; no range is a sum of other ranges.${npNote}</div>`);
  }
  // The Projection tab, in order: the WAR path (fan chart, upside, two-way
  // note), then the components (PJ_7), then the contract and FA blocks. The
  // aging explainer (AG_17) appends its block right after componentBlock.
  function projectionPanel(p) {
    const pr = p.proj || {};
    const twoWayNote = (p.twoWay && pr.warHit && pr.warPit)
      ? `<div class="fa-note">Two-way: the path sums hitting (${pr.warHit.map(fmtWar).join(" / ")}) and pitching (${pr.warPit.map(fmtWar).join(" / ")}).</div>` : "";
    return fanChart(p) + upsidePath(p) + twoWayNote + componentBlock(p) + contractBlock(p) + faBlock(p);
  }

  // A tab named "Projection & Contract" showed no contract for every player who
  // is not a free agent, because faBlock returns "" without a p.fa block. This
  // is composition of renderers that already ship: the guarantee line, the club
  // control line and the salary path strip that owns the dashed idiom.
  function contractBlock(p) {
    const pr = p.proj || {};
    const strip = salaryStripHtml(pr, { cls: "mlbp-sp" });
    const ctThru = pr.ctrlThru != null ? pr.ctrlThru
      : (Math.max(pr.thru || 0, pr.salThru || 0) || null);
    if (!strip && ctThru == null) return "";
    const open = pr.ctrlThru != null ? !!pr.ctrlOpen : !!pr.salTrunc;
    const cells = [
      ["Guaranteed thru", pr.thru != null ? String(pr.thru) : "no deal on file"],
      ["AAV", pr.aav != null ? `${money(pr.aav)}/yr` : EM_DASH],
      ["Club control thru", ctThru == null ? EM_DASH : `${ctThru}${open ? "+" : ""}`],
      ["Basis", pr.salSrc && pr.salSrc !== "pending" ? esc(String(pr.salSrc).replace(/_/g, " ")) : EM_DASH],
    ];
    const _why = pr.ctrlWhy || (pr.salTrunc || null);
    const _floor = open
      ? (_why === "no_prior_salary"
          ? " No season of the window carries a salary to raise the first arbitration award from, so the control end shown is a floor."
          : " The published arbitration grid ends on a pre-arbitration season, so the control end shown is a floor.")
      : "";
    const note = ctThru != null && pr.thru != null && ctThru > pr.thru
      ? `<div class="fa-sub mlbp-block-foot">${unsignedSpanText(pr, pr.thru + 1, ctThru)} They are drawn with a dashed border.${_floor}</div>`
      : open
      ? `<div class="fa-sub mlbp-block-foot">${_floor.trim()}</div>`
      : "";
    const band = (pr.surSalLo != null && pr.surSalHi != null)
      ? `<div class="fa-sub mlbp-block-foot">If the award lands at the band ends: ${money(pr.surSalLo)} to ${money(pr.surSalHi)}.</div>` : "";
    const _tl = horizonTail(pr);
    const _tp = _tl ? null : pricedTail(pr);
    const tailNote = _tl
      ? `<div class="fa-sub mlbp-block-foot" data-proj-horizon-tail>Surplus prices ${_tl.first}-${_tl.end} only. ${horizonTailText(pr, _tl)}</div>`
      : _tp
      ? `<div class="fa-sub mlbp-block-foot" data-proj-contract-tail>Surplus prices the whole guarantee, ${_tp.first}-${_tp.end}. ${pricedTailText(_tp)}</div>` : "";
    return section("contract-ctrl", "Contract", `${term("salary_path", "salary path")} · ${term("club_control_window", "club control window")}`,
      `<div class="mlbp-grid">${cells.map(([l, v]) => `<div class="mlbp-cell"><span class="mlbp-cell-label">${l}</span><span class="mlbp-cell-val">${v}</span></div>`).join("")}</div>${strip}${note}${tailNote}${band}`);
  }

  // ---- hitting ---------------------------------------------------------------
  // .262 style: three places, no leading zero. pct1: one place and a % sign.
  function rate3(v) {
    return v == null || !Number.isFinite(Number(v)) ? EM_DASH : Number(v).toFixed(3).replace(/^0(?=\.)/, "");
  }
  function pct1(v) {
    return v == null || !Number.isFinite(Number(v)) ? EM_DASH : Number(v).toFixed(1) + "%";
  }
  function arsenalTable(ar, extra) {
    const table = (ar && ar.length)
      ? `<table class="detail-table"><thead><tr><th>Pitch</th><th>Usage</th><th title="Savant pitcher run value per 100 pitches, pitcher view: positive = runs saved">RV/100</th><th>Whiff%</th><th>BA against</th></tr></thead>
      <tbody>${ar.map(a => `<tr><td>${esc(a.pitch || "")}</td><td>${a.usage != null ? a.usage.toFixed(1) + "%" : EM_DASH}</td>
        <td class="${a.rv100 != null && a.rv100 > 0 ? "proj-pos" : a.rv100 < 0 ? "proj-neg" : ""}">${a.rv100 != null ? a.rv100.toFixed(1) : EM_DASH}</td>
        <td>${a.whiff != null ? a.whiff.toFixed(1) + "%" : EM_DASH}</td><td>${rate3(a.ba)}</td></tr>`).join("")}</tbody></table>` : "";
    const tiles = extra ? `<div class="mlbp-tiles mlbp-tiles-left">${extra}</div>` : "";
    if (!table && !tiles) return "";
    return section("pitching-arsenal", "Pitch Arsenal", "usage · run value /100 (positive = runs saved) · whiff%", `<div class="mlbp-table-wrap">${table}</div>${tiles}`);
  }
  // Season stat lines, eWAR last (owner decision 20, 2026-09-11: the column is
  // restored and the Value tab keeps its WAR-by-season bars with the bWAR tick).
  // `war` is the served eWAR for that side of the card: a two-way card's
  // hitting table shows hitting eWAR and its pitching table pitching eWAR.
  // FanGraphs WAR (owner answer EPOCH-Q4): FanGraphs' published WAR as a
  // reference column after eWAR, shown only when a row on this table has a
  // published value; a row without one prints the null marker. eWAR stays the
  // site's WAR: the reference column never sorts, sums or bands anything.
  const IP_TIP = "Innings pitched in baseball notation: .1 and .2 are one and two outs";
  function seasonLines(rows, isPit, sid, sub) {
    const c = rows || [];
    if (!c.length) return "";
    const hasFg = c.some(r => r && r.war_fwar != null);
    // eWAR v3 (EBR_GATE.md 11.10.5): eWAR realized beside eWAR, then eWAR v2 and
    // bWAR as reference columns; present only when the payload carries them.
    const hasReal = c.some(r => r && r.war_real != null);
    const hasV2 = c.some(r => r && r.war_ewar2 != null);
    const bref = r => (r.war_bwar != null ? r.war_bwar : r.war);
    const warTh = `<th>${term("ewar", "eWAR")}</th>`
      + (hasReal ? `<th class="mlbp-realwar" title="${esc(REAL_WAR_TIP)}">${term("ewar_realized", "eWAR realized")}</th>` : "")
      + (hasV2 ? `<th class="mlbp-fgwar" title="${esc(V2_WAR_TIP)}">eWAR v2</th>` : "")
      + (hasFg ? `<th class="mlbp-fgwar" title="${esc(FG_WAR_TIP)}">FanGraphs WAR</th>` : "")
      + (hasReal ? `<th class="mlbp-fgwar" title="${esc(BREF_WAR_TIP)}">bWAR</th>` : "");
    const warTd = r => `<td>${r.war != null ? fmtWar(r.war) : EM_DASH}</td>`
      + (hasReal ? `<td class="mlbp-realwar">${r.war_real != null ? fmtWar(r.war_real) : EM_DASH}</td>` : "")
      + (hasV2 ? `<td class="mlbp-fgwar">${r.war_ewar2 != null ? fmtWar(r.war_ewar2) : EM_DASH}</td>` : "")
      + (hasFg ? `<td class="mlbp-fgwar">${r.war_fwar != null ? fmtWar(r.war_fwar) : EM_DASH}</td>` : "")
      + (hasReal ? `<td class="mlbp-fgwar">${bref(r) != null ? fmtWar(bref(r)) : EM_DASH}</td>` : "");
    const head = isPit
      ? `<th>Year</th><th title="${IP_TIP}">IP</th><th>ERA</th><th>K%</th><th>BB%</th>` + warTh
      : "<th>Year</th><th>PA</th><th>AVG/OBP/SLG</th><th>OPS</th><th>HR</th><th>SB</th><th>BB%</th><th>K%</th><th>ISO</th>" + warTh;
    const body = c.slice().reverse().map(r => isPit
      ? `<tr><td>${r.y}</td><td>${r.ip ?? EM_DASH}</td><td>${r.era != null ? r.era.toFixed(2) : EM_DASH}</td><td>${pct1(r.kPct)}</td><td>${pct1(r.bbPct)}</td>${warTd(r)}</tr>`
      : `<tr><td>${r.y}</td><td>${r.pa ?? EM_DASH}</td><td>${esc(r.avg || "-")}/${esc(r.obp || "-")}/${esc(r.slg || "-")}</td><td>${esc(r.ops || EM_DASH)}</td><td>${r.hr ?? EM_DASH}</td><td>${r.sb ?? EM_DASH}</td><td>${pct1(r.bbPct)}</td><td>${pct1(r.kPct)}</td><td>${rate3(r.iso)}</td>${warTd(r)}</tr>`).join("");
    return section(sid, "Season lines", sub,
      `<div class="mlbp-table-wrap"><table class="detail-table"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`);
  }
  function hittingIndexBlock(p) {
    const h = (p.skills || {}).hem;
    if (!h) return "";
    const ruler = rulerHTML([
      { label: "HEM+", v: h.hemPlus, gl: "hem_plus" },
      // The note is the plain difference of the two dots on this ruler,
      // computed here. It is NOT the board's Luck column: that is xwOBA
      // minus wOBA in wOBA points since 2026-09-24, because HEM+ is shrunk
      // and xHEM+ is not, so this difference partly measures the shrink.
      { label: "xHEM+", v: h.xhemPlus, gl: "xhem_plus", note: (h.xhemPlus != null && h.hemPlus != null) ? `${signed(h.xhemPlus - h.hemPlus, 0)} vs HEM+` : "" },
      { label: "xHEM+ Blend", v: h.fwdhemPlus, gl: "fwdhem_plus" },
      { label: "wRC+", v: h.wrcPlus, gl: "wrc_plus" },
      { label: "HEM+ 3yr", v: h.hemPlus3yr, gl: "hem_plus_3yr" },
    ], "ratio");
    if (!ruler) return "";
    const note = [h.pa != null ? `${h.pa} PA` : "", h.qualified ? "qualified" : "",
      h.pwoba != null ? `${term("pwoba", "pWOBA")} ${Number(h.pwoba).toFixed(3).replace(/^0(?=\.)/, "")}` : ""].filter(Boolean);
    note.push(`<a class="fa-player-link" href="/mlbstats/#section=hitters">MLB Stats &rarr;</a>`);
    return section("hitting-index", "Offense index", `${h.season ? esc(String(h.season)) + " · " : ""}100 = PA-weighted average of 50+ PA hitters`,
      ruler + `<div class="fa-sub mlbp-index-note">${note.join(" · ")}</div>`);
  }
  function swingTiles(p) {
    let out = "";
    if (p.swingPlus != null)
      out += tileHTML("Swing+", `${p.swingPlus}<span class="fa-band"> n=${p.swingN}</span>`,
        p.swingPlus >= 105 ? "proj-pos" : p.swingPlus <= 95 ? "proj-neg" : "", { gl: "swing_plus" });
    // Per-season Swing+ (display only; the pooled tile is the served number).
    // * marks a season under 180 swings, shrunk hard toward 100.
    if (p.swingPlusSeasons) {
      const sy = Object.keys(p.swingPlusSeasons).filter(y => (p.swingPlusSeasons[y] || {}).swing_plus != null).sort();
      if (sy.length >= 2) {
        const seg = sy.map(y => `${y.slice(2)}: ${Math.round(p.swingPlusSeasons[y].swing_plus)}${p.swingPlusSeasons[y].low_n ? "*" : ""}`).join(" / ");
        const sd = p.swingPlusSeasons[sy[sy.length - 1]].swing_plus - p.swingPlusSeasons[sy[sy.length - 2]].swing_plus;
        out += tileHTML("Swing+ trend", `<span class="mlbp-swing-seasons">${seg}</span>`,
          sd >= 5 ? "proj-pos" : sd <= -5 ? "proj-neg" : "", { gl: "swing_plus" });
      }
    }
    return out;
  }
  // Leverage and deployment: descriptive game context, not a skill index, so it
  // sits in its own block and is never banded on a plus ruler.
  function gameContextBlock(p, side) {
    const sk = p.skills || {};
    const cells = [];
    const cell = (label, val, gl) => cells.push(`<div class="mlbp-cell"><span class="mlbp-cell-label">${term(gl, label)}</span><span class="mlbp-cell-val">${val}</span></div>`);
    let season = null, hasWpa = false;
    if (side === "hit") {
      const L = sk.lev;
      if (L && L.kind === "bat") {
        season = L.season;
        if (L.wpa != null) cell("WPA", signed(L.wpa, 2), "wpa");
        if (L.wpaLi != null) cell("WPA/LI", signed(L.wpaLi, 2), "wpa_li");
        if (L.pli != null) cell("pLI", Number(L.pli).toFixed(2), "pli");
        if (L.clutch != null) cell("Clutch", signed(L.clutch, 2), "clutch");
      }
    } else {
      const s = pitchSkill(p);
      if (s && s.kind === "rel") {
        season = s.season;
        if (s.gmli != null) cell("gmLI", Number(s.gmli).toFixed(2) + (s.gmli3yr != null ? `<span class="fa-band"> 3yr ${Number(s.gmli3yr).toFixed(2)}</span>` : ""), "gmli");
        if (s.sd != null || s.md != null) cell("SD / MD", `${s.sd ?? 0} / ${s.md ?? 0}`, "shutdowns_meltdowns");
        if (s.wpa != null) { cell("WPA", signed(s.wpa, 2), "wpa"); hasWpa = true; }
      }
      const L = p.twoWay ? sk.levPit : sk.lev;
      if (L && L.kind === "sp") {
        season = season || L.season;
        if (L.wpa != null && !hasWpa) cell("WPA", signed(L.wpa, 2), "wpa");
        if (L.wpaLi != null) cell("WPA/LI", signed(L.wpaLi, 2), "wpa_li");
        if (L.wpaPerStart != null) cell("WPA/start", signed(L.wpaPerStart, 3), "wpa");
      }
    }
    if (!cells.length) return "";
    return section(side === "hit" ? "hitting-context" : "pitching-context", "Game context",
      `${season ? esc(String(season)) + " · " : ""}descriptive`,
      `<div class="mlbp-grid mlbp-grid-flow">${cells.join("")}</div>`);
  }
  function hittingPanel(p) {
    const head = p.twoWay ? `<div class="mlbp-section-title mlbp-subhead">As a hitter</div>` : "";
    const idx = hittingIndexBlock(p);
    const swing = swingTiles(p);
    const bs = batSpeedChip(p);
    const bat = (swing || bs)
      ? `<div class="mlbp-section" data-mlbp-section="hitting-bat"><div class="mlbp-section-title">Bat tracking <span class="fa-sub">MLB 2024+${p.swingPlusSeasons ? " · * under 180 swings" : ""}</span></div>`
        + `${swing ? `<div class="mlbp-tiles mlbp-tiles-left">${swing}</div>` : ""}${slotHTML("batspeed", bs)}</div>`
      : slotHTML("batspeed", "");
    const sc = sliders(p.sc, "hitting-statcast");
    const br = baserunningBlock(p);
    const ctx = gameContextBlock(p, "hit");
    const lines = seasonLines(p.career, false, "hitting-lines", "MLB · hitting");
    return { content: idx + swing + bs + sc + br + ctx + lines, html: head + idx + bat + sc + br + ctx + lines };
  }

  // ---- baserunning (a section of the Hitting tab, no tab of its own) --------
  // eBR and its three parts on run bars with eBR as the total, FanGraphs' BsR
  // and Savant's BRV as neutral comparison rows (the Defense tab's
  // "Positional (FG)" precedent: two systems, never one number), one line of
  // counts and rates, and the board link. Every value is the baked skills.br
  // block (mlb_player_export, read off the Baserunning board while
  // baserunning_export.CARD_BASERUNNING_LIVE is on); without the block the
  // section is absent and the tab is the tab it was. Descriptive: what
  // happened this season, on this season's run expectancy, not a forecast.
  function baserunningBlock(p) {
    const b = (p.skills || {}).br;
    if (!b || b.ebr == null) return "";
    const yr = b.season ? esc(String(b.season)) : "";
    const pct = v => (v == null ? null : `${(Number(v) * 100).toFixed(1)}%`);
    const bars = runBars([
      { label: "SB runs", v: b.ebrSb, gl: "ebr_sb" },
      { label: "XB runs", v: b.ebrXb, gl: "ebr_xb" },
      { label: "DP runs", v: b.ebrDp, gl: "ebr_dp" },
      { label: "eBR", v: b.ebr, gl: "ebr", total: true },
      b.bsrFg != null ? { label: "BsR (FG, published)", v: b.bsrFg, gl: "bsr", neutral: true, sub: true } : null,
      b.brvSavant != null ? { label: "BRV (Savant)", v: b.brvSavant, gl: "savant_brv", neutral: true, sub: true } : null,
    ]);
    const line = [
      b.sb != null ? `${esc(String(b.sb))} SB / ${esc(String(b.cs == null ? 0 : b.cs))} CS${b.sbPct != null ? ` (${pct(b.sbPct)})` : ""}` : "",
      b.pk ? `${esc(String(b.pk))} PK` : "",
      b.attRate != null ? `Att% ${pct(b.attRate)}` : "",
      b.xbtPct != null ? `XBT% ${pct(b.xbtPct)}` : "",
      b.gidpPct != null ? `GIDP% ${pct(b.gidpPct)}` : "",
      b.sprint != null ? `Sprint ${Number(b.sprint).toFixed(1)} ft/s${b.sprintPct != null ? ` (p${esc(String(b.sprintPct))})` : ""}` : "",
      `<a class="fa-player-link" href="/mlbstats/#section=baserunning">Baserunning board &rarr;</a>`,
    ].filter(Boolean);
    const pub = [b.bsrFg != null ? "BsR" : "", b.brvSavant != null ? "BRV" : ""].filter(Boolean);
    return section("hitting-baserunning", "Baserunning",
      `${yr ? yr + " · " : ""}${b.qualified ? "qualified" : "provisional"} · eBR ours, from MLB play-by-play`
        + (pub.length ? ` · ${pub.join(" and ")} published, not computed here` : ""),
      `<div class="fa-sub mlbp-index-note">${line.join(" · ")}</div>${bars}`);
  }

  // ---- pitching --------------------------------------------------------------
  // Live season pitching from the /mlbstats/ leaderboards (REM+ / RIV+ for
  // relievers, SEM+ for starters), joined by MLBAM. Prefer the baked skills
  // block; payloads generated before the bake fall back to the client-fetched
  // leaderboard rows, which land in the pitchlb slot.
  function ensurePitchingStats() {
    if (PITCHLB || PITCHLB_LOADING) return;
    PITCHLB_LOADING = true;
    const byMlbam = {};
    const grab = (url, kind) => fetch(url, { cache: "no-cache" })
      .then(r => (r.ok ? r.json() : null))
      .then(d => {
        const rows = (d && (d.relievers || d.starters)) || [];
        const season = d && d.season;
        rows.forEach(row => { if (row.mlbam != null) byMlbam[row.mlbam] = { kind, season, row }; });
      })
      .catch(() => {});
    Promise.all([
      grab("/data/bullpen_leaderboards.json", "rel"),
      grab("/data/starter_leaderboards.json", "sp"),
    ]).then(() => {
      PITCHLB = { byMlbam };
      PITCHLB_LOADING = false;
      const cur = currentCard();
      if (cur && (cur.isPit || cur.twoWay)) patchSlot("pitchlb", state.player, pitchingIndexBlock(cur));
    });
  }
  function pitchSkill(p) {
    if (!p || p.mlbam == null) return null;
    if (p.skills && p.skills.pitch) return p.skills.pitch;
    const hit = PITCHLB && PITCHLB.byMlbam && PITCHLB.byMlbam[p.mlbam];
    if (!hit) return null;
    const r = hit.row;
    return { kind: hit.kind, season: hit.season, role: r.role, ip: r.ip,
      remPlus: r.rem_plus, rivPlus: r.riv_plus, remPlus3yr: r.rem_plus_3yr, xremPlus: r.xrem_plus,
      semPlus: r.sem_plus, semPlus3yr: r.sem_plus_3yr, xsemPlus: r.xsem_plus,
      warIpPlus: r.war_ip_plus, warIpPlusAdj: r.war_ip_plus_adj, warIpPlusPct: r.war_ip_plus_pct,
      warIpPlus3yr: r.war_ip_plus_3yr, gmli: r.gmli, gmli3yr: r.gmli_3yr,
      saves: r.saves, holds: r.holds, wpa: r.wpa, sd: r.sd, md: r.md, gs: r.gs, ipPerGs: r.ip_per_gs };
  }
  // Decimal innings (174.333) in the baseball notation the season lines use
  // (174.1): the digit after the point counts outs.
  function ipThirds(v) {
    const n = Number(v);
    if (!Number.isFinite(n)) return EM_DASH;
    let whole = Math.floor(n + 1e-9), outs = Math.round((n - whole) * 3);
    if (outs >= 3) { whole += 1; outs = 0; }
    return `${whole}.${outs}`;
  }
  // Starters and relievers are separate pools; their indexes never share an axis.
  function pitchingIndexBlock(p) {
    const s = pitchSkill(p);
    if (!s) return "";
    const rel = s.kind === "rel";
    const ruler = rulerHTML(rel
      ? [{ label: "REM+", v: s.remPlus, gl: "rem_plus" }, { label: "RIV+", v: s.rivPlus, gl: "riv_plus" },
        { label: "xREM+", v: s.xremPlus, gl: "xrem_plus" }, { label: "REM+ 3yr", v: s.remPlus3yr, gl: "rem_plus_3yr" }]
      : [{ label: "SEM+", v: s.semPlus, gl: "sem_plus" }, { label: "xSEM+", v: s.xsemPlus, gl: "xsem_plus" },
        { label: "SEM+ 3yr", v: s.semPlus3yr, gl: "sem_plus_3yr" }], "run");
    if (!ruler) return "";
    const line = [esc(s.role || (rel ? "reliever" : "starter")),
      s.ip != null ? `${ipThirds(s.ip)} IP` : "",
      !rel && s.gs != null ? `${esc(String(s.gs))} GS` : "",
      !rel && s.ipPerGs != null ? `${Number(s.ipPerGs).toFixed(1)} IP/GS` : "",
      rel && (s.saves != null || s.holds != null) ? `${s.saves || 0} SV / ${s.holds || 0} HLD` : "",
      `<a class="fa-player-link" href="/mlbstats/#section=${rel ? "bullpen" : "starters"}">MLB Stats &rarr;</a>`].filter(Boolean);
    return section("pitching-index", "Run prevention",
      `${s.season ? esc(String(s.season)) + " · " : ""}100 = ${rel ? "reliever" : "starter"} pool average`,
      `<div class="fa-sub mlbp-index-note">${line.join(" · ")}</div>${ruler}`);
  }
  function pitchingPanel(p) {
    const head = p.twoWay ? `<div class="mlbp-section-title mlbp-subhead">As a pitcher</div>` : "";
    const idx = pitchingIndexBlock(p);
    const sc = sliders(p.twoWay ? p.scPit : p.sc, "pitching-statcast");
    const astuff = p.aaaStuffPlus != null
      ? tileHTML("aStuff+", `${Math.round(p.aaaStuffPlus)}<span class="fa-band"> AAA ${esc(String(p.aaaStuffSeason || ""))}</span>`,
        p.aaaStuffPlus >= 110 ? "proj-pos" : p.aaaStuffPlus <= 90 ? "proj-neg" : "", { gl: "stuff_plus_aaa" }) : "";
    const ars = arsenalTable(p.arsenal, astuff);
    const ctx = gameContextBlock(p, "pit");
    const lines = seasonLines(p.twoWay ? p.careerPit : p.career, true, "pitching-lines", "MLB · pitching");
    return { content: idx + sc + ars + ctx + lines, html: head + slotHTML("pitchlb", idx) + sc + ars + ctx + lines };
  }

  // ---- defense ---------------------------------------------------------------
  // DEM+ (100 + 10z) on the z ruler, FanGraphs' published fielding and framing
  // runs, and the positional term Def uses, which is OUR ladder (Position Fit,
  // owner decision 18, 2026-09-11), as their own labelled rows. Two quantities,
  // never combined into one number here; nothing on this tab feeds a prospect
  // grade.
  function defensePanel(p) {
    const d = (p.skills || {}).def;
    const scBlock = statcastCatcherBlock(p);
    const sc = slotHTML("sccatcher", scBlock);
    if (!d || (d.demPlus == null && d.defRuns == null && d.fldTotal == null)) return scBlock ? sc : "";
    const yr = d.season ? esc(String(d.season)) : "";
    const pos = esc(d.pos || "");
    const pct = [d.demPlusPct != null ? `p${d.demPlusPct} MLB` : "", d.demPlusPosPct != null && pos ? `p${d.demPlusPosPct} ${pos}` : ""].filter(Boolean).join(" · ");
    const dem = d.demPlus != null
      ? tileHTML("DEM+", esc(String(d.demPlus)), bandCls(d.demPlus, "z"), { gl: "dem_plus", sub: pct }) : "";
    const board = `<a class="fa-player-link" href="/mlbstats/#section=defense">Defense board &rarr;</a>`;
    const demSec = section("defense-dem", "Defense index",
      [yr, d.qualified ? "qualified" : "provisional", board].filter(Boolean).join(" · "),
      dem ? `<div class="mlbp-tiles mlbp-tiles-left">${dem}</div>` : "");
    const runs = section("defense-runs", "Runs", `fielding and framing FanGraphs published · positional our ladder${yr ? " · " + yr : ""}`, runBars([
      { label: "Fielding", v: d.fldTotal, gl: "fielding_runs" },
      d.frmRuns != null ? { label: "Framing (in Fielding)", v: d.frmRuns, gl: "framing_runs", sub: true } : null,
      { label: "Positional (ours)", v: d.posRuns, gl: "positional_adjustment", neutral: true },
      d.posRunsFg != null ? { label: "Positional (FG)", v: d.posRunsFg, gl: "positional_adjustment", neutral: true, sub: true } : null,
      { label: "Def", v: d.defRuns, total: true },
    ]));
    const pi = d.posInn ? Object.entries(d.posInn).filter(([, v]) => Number(v) > 0).sort((a, b) => b[1] - a[1]) : [];
    const chips = pi.map(([ps, v]) => `<span class="position-usage-chip"><span>${esc(ps)}</span>:${fmtInn(v)}</span>`).join("");
    const posSec = section("defense-positions", "Positions", `innings${yr ? " · " + yr : ""}`,
      chips ? `<div class="position-usage-strip">${chips}${d.inn != null ? `<span class="fa-sub">${fmtInn(d.inn)} total</span>` : ""}</div>` : "");
    return demSec + runs + posSec + sc;
  }

  // Statcast catcher runs by season (owner decision EW3-38, 2026-10-16): the
  // catcher's framing, blocking and throwing run values and their total at C,
  // Statcast's published whole runs as FanGraphs carries them, verbatim. A
  // measurement with no model claim; nothing on this tab sums it with the
  // FanGraphs rows above. Fetched once, after the first paint, into its slot.
  function ensureStatcastCatcher() {
    if (SCC || SCC_LOADING) return;
    SCC_LOADING = true;
    fetch("/data/statcast_catcher_runs.json", { cache: "no-cache" })
      .then(r => (r.ok ? r.json() : null))
      .then(d => {
        const at = {};
        ((d && d.fields) || []).forEach((k, i) => { at[k] = i; });
        SCC = { at, players: (d && d.players) || {} };
        SCC_LOADING = false;
        const cur = currentCard();
        if (cur && (!cur.isPit || cur.twoWay)) patchSlot("sccatcher", state.player, statcastCatcherBlock(cur));
      })
      .catch(() => { SCC = { at: {}, players: {} }; SCC_LOADING = false; });
  }
  function statcastCatcherBlock(p) {
    if (!SCC || !p || p.mlbam == null) return "";
    const a = SCC.at;
    const rows = (SCC.players[String(p.mlbam)] || []).filter(r => Array.isArray(r) && r[a.season] != null);
    if (a.season == null || !rows.length) return "";
    const sg = v => (v == null || !isFinite(v)) ? EM_DASH : esc((Number(v) > 0 ? "+" : "") + Math.round(Number(v)));
    const body = rows.slice().sort((x, y) => y[a.season] - x[a.season]).map(r =>
      `<tr><td>${esc(String(r[a.season]))}</td><td>${fmtInn(r[a.inn])}</td><td>${sg(r[a.frm])}</td>`
      + `<td>${sg(r[a.blk])}</td><td>${sg(r[a.thr])}</td><td><b>${sg(r[a.tot])}</b></td></tr>`).join("");
    const head = `<th>Year</th><th>Inn at C</th><th>Framing</th><th>Blocking</th><th>Throwing</th>`
      + `<th>${term("statcast_catcher_runs", "Statcast runs")}</th>`;
    return section("defense-statcast-c", "Statcast catcher runs",
      "Statcast's published run values at C, as FanGraphs carries them · not computed here · blocking from 2018",
      `<div class="mlbp-table-wrap"><table class="detail-table" data-statcast-c><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`);
  }

  // ---- value -----------------------------------------------------------------
  function valueRatesBlock(p) {
    const sk = p.skills || {};
    const h = (!p.isPit || p.twoWay) ? sk.hem : null;
    const s = (p.isPit || p.twoWay) ? pitchSkill(p) : null;
    const t = [];
    if (h) {
      if (h.warPaPlus != null) t.push(tileHTML("WAR/PA+", esc(String(h.warPaPlus)), bandCls(h.warPaPlus, "z"), { gl: "war_pa_plus", sub: h.warPaPlusPct != null ? `p${h.warPaPlusPct}` : "" }));
      if (h.warPaPlusAdj != null) t.push(tileHTML("WAR/PA+ adj", esc(String(h.warPaPlusAdj)), bandCls(h.warPaPlusAdj, "z"), { gl: "war_pa_plus_adj" }));
      if (h.warPaPlus3yr != null) t.push(tileHTML("WAR/PA+ 3yr", esc(String(h.warPaPlus3yr)), bandCls(h.warPaPlus3yr, "z"), { gl: "war_pa_plus_3yr" }));
    }
    if (s) {
      // Anchored on the pitcher's own role pool: a starter's and a reliever's
      // WAR/IP+ are not comparable.
      const g = s.kind === "rel"
        ? ["war_ip_plus_rp", "war_ip_plus_rp_adj", "war_ip_plus_rp_3yr"]
        : ["war_ip_plus_sp", "war_ip_plus_sp_adj", "war_ip_plus_sp_3yr"];
      if (s.warIpPlus != null) t.push(tileHTML("WAR/IP+", esc(String(s.warIpPlus)), bandCls(s.warIpPlus, "z"), { gl: g[0], sub: s.warIpPlusPct != null ? `p${s.warIpPlusPct}` : "" }));
      if (s.warIpPlusAdj != null) t.push(tileHTML("WAR/IP+ adj", esc(String(s.warIpPlusAdj)), bandCls(s.warIpPlusAdj, "z"), { gl: g[1] }));
      if (s.warIpPlus3yr != null) t.push(tileHTML("WAR/IP+ 3yr", esc(String(s.warIpPlus3yr)), bandCls(s.warIpPlus3yr, "z"), { gl: g[2] }));
    }
    return section("value-rates", "Rate indexes", "100 + 10z", t.length ? `<div class="mlbp-tiles mlbp-tiles-left">${t.join("")}</div>` : "");
  }
  function valuePanel(p) {
    const ss = warSeasons(p);
    const chart = warBarsSVG(ss, p.twoWay ? ["hitting", "pitching"] : null);
    const legend = (chart && p.twoWay)
      ? `<div class="fa-sub mlbp-legend"><span><i class="mlbp-legend-swatch"></i>hitting</span><span><i class="mlbp-legend-swatch mlbp-legend-b"></i>pitching</span></div>` : "";
    const hasRef = ss.some(s => s.refA != null || s.refB != null);
    return section("value-war", "WAR by season", `${term("ewar", "eWAR")}${hasRef ? " · tick = bWAR" : ""}`, chart ? chart + legend : "")
      + valueRatesBlock(p);
  }

  // ---- overview --------------------------------------------------------------
  // One screen for the reader who never clicks: a lens per question, each
  // opening the tab that owns it, and the two season arcs.
  function overviewPanel(p, key) {
    const sk = p.skills || {};
    const hitSide = !p.isPit || !!p.twoWay, pitSide = !!p.isPit || !!p.twoWay;
    const lenses = [];
    // .mlbp-lens-num sets colour AND weight 800 at one class, and it is declared
    // after the ruler block, so a one-class .vt-* colour rule loses to it on
    // source order. Every tiered lens therefore paints an INNER span; only the
    // untiered Value lens takes the plain form. This is why the ratio lens used
    // to look uncoloured with proj-pos sitting right there in its class list.
    const lensNum = (num, cls) => (cls
      ? `<span class="mlbp-lens-num"><span class="${cls}">${num}</span></span>`
      : `<span class="mlbp-lens-num">${num}</span>`);
    const lens = (goto, head, num, cls, label, sub) => lenses.push(
      `<div class="mlbp-lens"><button type="button" class="mlbp-lens-head" data-mlbp-goto="${goto}">${head} &rarr;</button>`
      + `<div class="mlbp-lens-val">${lensNum(num, cls)}${label}</div>`
      + (sub ? `<div class="mlbp-lens-sub">${sub}</div>` : "") + `</div>`);
    const h = hitSide ? sk.hem : null;
    if (h && h.hemPlus != null)
      lens("hitting", "Offense", esc(String(h.hemPlus)), bandCls(h.hemPlus, "ratio"), term("hem_plus", "HEM+"),
        [h.wrcPlus != null ? `wRC+ ${esc(String(h.wrcPlus))}` : "", h.xhemPlus != null ? `xHEM+ ${esc(String(h.xhemPlus))}` : ""].filter(Boolean).join(" · "));
    const s = pitSide ? pitchSkill(p) : null;
    if (s) {
      const rel = s.kind === "rel";
      const v = rel ? s.remPlus : s.semPlus;
      if (v != null)
        lens("pitching", "Run prevention", esc(String(v)), bandCls(v, "run"), term(rel ? "rem_plus" : "sem_plus", rel ? "REM+" : "SEM+"),
          [rel ? (s.rivPlus != null ? `RIV+ ${esc(String(s.rivPlus))}` : "") : (s.xsemPlus != null ? `xSEM+ ${esc(String(s.xsemPlus))}` : ""),
            s.ip != null ? `${esc(String(s.ip))} IP` : ""].filter(Boolean).join(" · "));
    }
    const d = hitSide ? sk.def : null;
    if (d && d.demPlus != null)
      lens("defense", "Defense", esc(String(d.demPlus)), bandCls(d.demPlus, "z"), term("dem_plus", "DEM+"),
        [d.fldTotal != null ? `${signed(d.fldTotal, 1)} fielding runs` : "", d.pos ? esc(d.pos) : ""].filter(Boolean).join(" · "));
    const ss = warSeasons(p);
    const last = ss[ss.length - 1];
    if (last)
      lens("value", "Value", fmtWar(warTot(last)), "", `${last.y} ${term("ewar", "eWAR")}`,
        h && h.warPaPlus != null ? `WAR/PA+ ${esc(String(h.warPaPlus))}` : (s && s.warIpPlus != null ? `WAR/IP+ ${esc(String(s.warIpPlus))}` : ""));
    const lensHTML = lenses.length
      ? `<div class="mlbp-section" data-mlbp-section="overview-lenses"><div class="mlbp-lenses">${lenses.join("")}</div></div>` : "";
    const opt = aria => ({ w: 240, h: 60, fmt: fmtWar, aria });
    const warTrend = miniTrendSVG(ss.map(x => ({ v: warTot(x), t: `${x.y}: ${fmtWar(warTot(x))} eWAR` })), opt("eWAR by season"));
    const pw = (p.proj && p.proj.war) || [];
    const first = DATA ? DATA.first_season : null;
    const projTrend = first != null
      ? miniTrendSVG(pw.map((v, t) => ({ v, t: `${first + t}: ${fmtWar(v)}` })), opt("Projected WAR, fWAR basis")) : "";
    const mini = (goto, label, svg) => (svg
      ? `<div class="mlbp-mini"><button type="button" class="mlbp-lens-head" data-mlbp-goto="${goto}">${label} &rarr;</button>${svg}</div>` : "");
    const minis = mini("value", `eWAR by season${ss.length ? ` <span class="fa-sub">${ss[0].y}-${last.y}</span>` : ""}`, warTrend)
      + mini("projection", `Projected WAR${pw.length && first != null ? ` <span class="fa-sub">${first}-${first + pw.length - 1}</span>` : ""}`, projTrend);
    const minisHTML = minis ? `<div class="mlbp-section" data-mlbp-section="overview-trends"><div class="mlbp-minis">${minis}</div></div>` : "";
    const hof = hofLine(p);
    const usage = positionGamesSummary(key);
    // The timeline slot exists only while the events feed is served (Q9_22b).
    const tl = timelineBlock(key);
    return { content: lensHTML + minisHTML + hof + usage + tl,
             html: lensHTML + minisHTML + hof + slotHTML("usage", usage) + (eventsLive() ? slotHTML("timeline", tl) : "") };
  }

  // ---- Hall of Fame line (wiring W05) -----------------------------------------
  // The /hof/ shelf's own row for a player on its Cooperstown Watch or Not Yet
  // Eligible band, baked by mlb_player_export._hof_index. The numbers are the
  // shelf's, printed at the shelf's precision, so this line and /hof/ agree.
  // The player's own numbers only: no position comparison (the shelf's position
  // groups have no 3B group). The band names a shelf band, not a forecast.
  function hofLine(p) {
    const HOF_BAND_LABEL = { watch: "Cooperstown Watch", not_yet_eligible: "Not Yet Eligible" };
    const h = p && p.hof;
    if (!h || !HOF_BAND_LABEL[h.band] || h.jaws == null) return "";
    const n1 = v => (v == null || !Number.isFinite(Number(v)) ? "" : Number(v).toFixed(1));
    const chip = (label, v) => (v === "" ? "" : `<span class="position-usage-chip">${label}&nbsp;${esc(v)}</span>`);
    const span = (h.first != null && h.last != null)
      ? `${esc(String(h.first))}-${esc(String(h.last))}${h.seasons != null ? `, ${esc(String(h.seasons))} seasons` : ""}` : "";
    return `<div class="position-usage-strip" data-mlbp-section="overview-hof">
      <span class="position-usage-label">Hall of Fame shelf</span>
      ${chip("<span>WAR</span>", n1(h.war))}${chip(`<span>${term("war7", "WAR7")}</span>`, n1(h.war7))}${chip(`<span>${term("jaws", "JAWS")}</span>`, n1(h.jaws))}${chip("<span>WAA+</span>", n1(h.waa_pos))}${chip(`<span>${term("war_ink", "WAR ink")}</span>`, h.ink == null ? "" : Number(h.ink).toFixed(0))}
      <span class="fa-sub">${esc(h.basis || "B-Ref bWAR")}${span ? `, ${span}` : ""}</span>
      <a class="fa-sub" href="/hof/">${esc(HOF_BAND_LABEL[h.band])} band on the Hall of Fame page &rarr;</a>
    </div>`;
  }

  // ---- hero ------------------------------------------------------------------
  // At most four tiles, the same four slots for every role: window WAR, surplus,
  // the primary skill index, and a second read (DEM+ for fielders, WAR/IP+ for
  // pitchers, the pitching index for a two-way card). A missing slot falls back
  // to the latest season's eWAR, then to nothing.
  function heroTiles(p) {
    const sk = p.skills || {}, pr = p.proj || {};
    const sum = a => (a || []).reduce((acc, v) => acc + (v || 0), 0);
    const out = [];
    if (pr.warTotal != null)
      out.push(tileHTML(`${(pr.war || []).length}y WAR`, fmtWar(pr.warTotal), "", { gl: "ewar",
        sub: (p.twoWay && pr.warHit && pr.warPit) ? `hit ${fmtWar(sum(pr.warHit))} / pit ${fmtWar(sum(pr.warPit))}` : "expected" }));
    const sv = surOf(p.proj);
    const tl = horizonTail(pr);
    const tp = tl ? null : pricedTail(pr);
    if (sv != null)
      out.push(tileHTML(
        (pr.surNpv == null && pr.surRos != null) ? "Surplus (rest of season)"
          : tl ? `Surplus (${tl.first}-${tl.end})`
          : tp ? `Surplus (${tp.first}-${tp.end})`
          : pr.salPath ? "Surplus (club control window)" : "Surplus NPV",
        money(sv), sv >= 0 ? "proj-pos" : "proj-neg",
        { gl: "surplus_value",
          sub: tl ? `${tl.n} guaranteed season${tl.n === 1 ? "" : "s"} after ${tl.end} not priced`
            : tp ? `${tp.from}-${tp.end} on the champion aging curve`
            : (pr.surSalLo != null && pr.surSalHi != null)
            ? `award band ${money(pr.surSalLo)} to ${money(pr.surSalHi)}` : "" }));
    const h = sk.hem, d = sk.def, s = (p.isPit || p.twoWay) ? pitchSkill(p) : null;
    const pitIdx = () => {
      if (!s) return "";
      if (s.kind === "rel")
        return s.remPlus != null ? tileHTML("REM+", esc(String(s.remPlus)), bandCls(s.remPlus, "run"), { gl: "rem_plus", sub: s.rivPlus != null ? `RIV+ ${esc(String(s.rivPlus))}` : "" }) : "";
      return s.semPlus != null ? tileHTML("SEM+", esc(String(s.semPlus)), bandCls(s.semPlus, "run"), { gl: "sem_plus", sub: s.semPlus3yr != null ? `3yr ${esc(String(s.semPlus3yr))}` : "" }) : "";
    };
    const seasonWar = () => {
      const ss = warSeasons(p), last = ss[ss.length - 1];
      return last ? tileHTML(`${last.y} WAR`, fmtWar(warTot(last)), "", { gl: "ewar" }) : "";
    };
    if (p.isPit && !p.twoWay) {
      out.push(pitIdx());
      out.push((s && s.warIpPlus != null)
        ? tileHTML("WAR/IP+", esc(String(s.warIpPlus)), bandCls(s.warIpPlus, "z"), { gl: s.kind === "rel" ? "war_ip_plus_rp" : "war_ip_plus_sp", sub: s.warIpPlusPct != null ? `p${s.warIpPlusPct}` : "" })
        : seasonWar());
    } else {
      if (h && h.hemPlus != null)
        out.push(tileHTML("HEM+", esc(String(h.hemPlus)), bandCls(h.hemPlus, "ratio"), { gl: "hem_plus", sub: h.hemPlus3yr != null ? `3yr ${esc(String(h.hemPlus3yr))}` : "" }));
      if (p.twoWay) out.push(pitIdx() || seasonWar());
      else if (d && d.demPlus != null)
        out.push(tileHTML("DEM+", esc(String(d.demPlus)), bandCls(d.demPlus, "z"), { gl: "dem_plus", sub: d.fldTotal != null ? `${signed(d.fldTotal, 1)} fielding runs` : "" }));
      else out.push(seasonWar());
    }
    return out.filter(Boolean).slice(0, 4).join("");
  }

  // ---- bat-speed change -----------------------------------------------------
  // MLB bat tracking starts in 2024, so a year-over-year Swing+ delta exists ONLY
  // for hitters with a scored season on BOTH sides of the latest pair. That is a
  // small, named population (the payload reports exactly how many), and every
  // other hitter gets an explicit no-data state instead of a chip that implies
  // coverage we do not have.
  //
  // The alert cut is the 10th percentile of the MEASURED delta distribution in
  // that same population, carried on the payload - a distributional flag, not a
  // validated predictor of anything. Nothing here claims a decline forecasts
  // decline; it says this season's swing is in the bottom tenth of observed
  // year-over-year changes.
  function ensureSwingDelta() {
    if (SWINGD || SWINGD_LOADING) return;
    SWINGD_LOADING = true;
    fetch("/data/swing_delta.json", { cache: "no-cache" })
      .then(r => (r.ok ? r.json() : null))
      .then(d => {
        SWINGD = d || { players: {} };
        SWINGD_LOADING = false;
        const cur = currentCard();
        if (cur && (!cur.isPit || cur.twoWay)) patchSlot("batspeed", state.player, batSpeedChip(cur));
      })
      .catch(() => { SWINGD = { players: {} }; SWINGD_LOADING = false; });
  }
  function batSpeedChip(p) {
    if (p.isPit && !p.twoWay) return "";           // bat tracking is a hitter read
    if (!SWINGD || !SWINGD.players) return "";
    const yrs = (SWINGD.priorSeason && SWINGD.latestSeason)
      ? `${String(SWINGD.priorSeason).slice(2)}&rarr;${String(SWINGD.latestSeason).slice(2)}` : "";
    const row = p.mlbam != null ? SWINGD.players[String(p.mlbam)] : null;
    const wrap = (cls, body, title) =>
      `<div class="mlbp-batspeed ${cls}" title="${esc(title)}">${body}</div>`;
    if (!row) {
      // Two distinct no-data cases, said plainly rather than blended.
      const why = (SWINGD.latestSeason && p.swingPlusSeasons
                   && (p.swingPlusSeasons[String(SWINGD.latestSeason)] || {}).swing_plus != null)
        ? `no ${SWINGD.priorSeason} bat-tracking season to compare against`
        : "no scored bat-tracking pair for this hitter";
      return wrap("is-nodata",
        `<span class="mlbp-batspeed-label">Bat speed ${yrs}</span><span class="mlbp-batspeed-val">no data</span>`
        + `<span class="mlbp-batspeed-why">${esc(why)}</span>`,
        `Needs a scored Swing+ season on both sides: ${SWINGD.n} hitters qualify `
        + `(${SWINGD.nLatestOnly} more have ${SWINGD.latestSeason} only). MLB bat tracking starts in 2024; no MiLB equivalent.`);
    }
    const cut = (SWINGD.dist || {}).p10;
    const alert = (cut != null && row.d <= cut);
    const sign = row.d > 0 ? "+" : "";
    const body = `<span class="mlbp-batspeed-label">Bat speed ${yrs}</span>`
      + `<span class="mlbp-batspeed-val">${sign}${row.d.toFixed(1)}</span>`
      + `<span class="mlbp-batspeed-why">Swing+ ${row.prior.toFixed(1)} &rarr; ${row.latest.toFixed(1)}`
      + `${row.lowN ? " &middot; partial tracking" : ""}</span>`
      + (alert ? `<span class="mlbp-batspeed-flag">bottom decile</span>` : "");
    const title = `Swing+ moved ${sign}${row.d.toFixed(1)} from ${SWINGD.priorSeason} (n=${row.nPrior} swings) to `
      + `${SWINGD.latestSeason} (n=${row.nLatest}). Across the ${SWINGD.n} hitters with both seasons the median change is `
      + `${(SWINGD.dist || {}).p50}, the 10th percentile ${cut} and the 90th ${(SWINGD.dist || {}).p90}. `
      + (alert ? "This change is in the bottom tenth. " : "")
      + "Descriptive; not tested as a predictor."
      + (row.lowN ? ` One season is under ${SWINGD.minSwings} swings and is shrunk toward 100.` : "");
    return wrap(alert ? "is-alert" : "", body, title);
  }

  function ensureFielding() {
    if (FIELDING || FIELDING_LOADING) return;
    FIELDING_LOADING = true;
    fetch("/data/mlb_position_games.json", { cache: "no-cache" })
      .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
      .then(d => {
        FIELDING = d || {};
        FIELDING_LOADING = false;
        if (state.player) patchSlot("usage", state.player, positionGamesSummary(state.player));
      })
      .catch(() => { FIELDING = { players: {} }; FIELDING_LOADING = false; });
  }
  // A graduate's final tracked-park Statcast hitter line (origin.aaaHit, from
  // the PROSPX hitter card's sidecar): the level and season it came from, the
  // through or as-of date that keeps a partial season from reading as the
  // full one, and the four contact numbers PROSPX prints, in its format.
  const AAA_MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  function aaaShortDate(d) {
    if (!d || !/^[0-9]{4}-[0-9]{2}-[0-9]{2}$/.test(d)) return "";
    const mon = AAA_MON[Number(d.slice(5, 7)) - 1];
    return mon ? `${mon} ${Number(d.slice(8, 10))}` : "";
  }
  function aaaHitLine(h) {
    if (!h || h.season == null) return "";
    const fx = (v, d) => (v != null && isFinite(v)) ? Number(v).toFixed(d) : null;
    const parts = [
      fx(h.xwoba, 3) != null ? `xwOBA ${fx(h.xwoba, 3)}` : "",
      fx(h.ev, 1) != null ? `EV ${fx(h.ev, 1)} mph` : "",
      fx(h.hardHit, 1) != null ? `HardHit% ${fx(h.hardHit, 1)}%` : "",
      fx(h.whiff, 1) != null ? `Whiff% ${fx(h.whiff, 1)}%` : "",
    ].filter(Boolean);
    if (!parts.length) return "";
    const lv = (Array.isArray(h.levels) && h.levels.length)
      ? h.levels.map(l => (l === "A" ? "A (FSL)" : String(l))).join(" + ") : "";
    const when = h.thru && aaaShortDate(h.thru) ? ` through ${aaaShortDate(h.thru)}`
      : h.asOf && aaaShortDate(h.asOf) ? ` as of ${aaaShortDate(h.asOf)}` : "";
    const head = [lv, `${esc(String(h.season))}${when}`].filter(Boolean).join(" ")
      + (h.pa != null ? `, ${esc(String(h.pa))} PA` : "");
    const title = "Baseball Savant minors Statcast, tracked parks only (every AAA park and the"
      + " Single-A Florida State League): his latest season with 100+ PA there, the line his"
      + " PROSPX card shows.";
    return `<div class="fa-sub mlbp-origin-line" title="${esc(title)}">Statcast (tracked parks), ${head}: ${parts.join(" · ")}</div>`;
  }
  // 20-80 scouting-scale color (50 = MLB average). Tool grades display CEILING.
  function gradeColor(v) {
    return v >= 65 ? "var(--up)" : v >= 55 ? "var(--accent-cyan)" : v >= 45 ? "var(--text-secondary)" : "var(--down)";
  }
  const TOOL_PILLS = {
    hit: [["Hit", "hit"], ["Game Pwr", "game_pwr"], ["Raw Pwr", "raw_pwr"], ["Speed", "speed"], ["Field", "field"], ["Arm", "throw"], ["Bat Ctrl", "bat_ctrl"], ["Pitch Sel", "pitch_sel"]],
    pit: [["FB", "fb"], ["SL", "sl"], ["CB", "cb"], ["CH", "ch"], ["CT", "ct"], ["CMD", "cmd"], ["FRM", "frame"], ["ATHL", "athl"]],
  };
  // eTools (ETOOLS_SITEWIDE_FLIP, owner decision EW3-27): the shown grade for each
  // tool with a passing eTool (hit, game power, pitch selection, bat control,
  // fastball, command), read from the payload PROSPX reads and printed to the
  // nearest whole grade; every other tool keeps its consensus grade, rounded up.
  // MLBP_ETOOLS_ON mirrors etools.ETOOLS_ON (a test pins the two); off, the pills
  // print exactly as before.
  const MLBP_ETOOLS_ON = true;
  let ETOOLS = null, ETOOLS_LOADING = false;
  function ensureETools() {
    if (!MLBP_ETOOLS_ON || ETOOLS || ETOOLS_LOADING) return;
    ETOOLS_LOADING = true;
    fetch("/data/etools.json", { cache: "no-cache" })
      .then(r => (r.ok ? r.json() : null))
      .then(d => {
        const players = (d && d.players) || {};
        const byMlbam = {};
        for (const k in players) if (players[k] && players[k].mlbam != null) byMlbam[String(players[k].mlbam)] = players[k];
        ETOOLS = { players, byMlbam };
        ETOOLS_LOADING = false;
        const cur = currentCard();
        if (cur) patchSlot("scouttools", state.player, scoutToolPills(cur));
      })
      .catch(() => { ETOOLS = { players: {}, byMlbam: {} }; ETOOLS_LOADING = false; });
  }
  function eToolsOf(p) {
    if (!MLBP_ETOOLS_ON || !ETOOLS) return {};
    const pk = p.origin && p.origin.prospx;
    const e = (pk && ETOOLS.players[pk]) || (p.mlbam != null ? ETOOLS.byMlbam[String(p.mlbam)] : null);
    return (e && e.side === (p.isPit ? "pit" : "hit")) ? (e.tools || {}) : {};
  }
  // The pill row: an eTool (marked e) where one passed, else the consensus grade
  // (marked c, rounded up); the consensus stays in the eTool's tooltip.
  function scoutToolPills(p) {
    const s = p.scout;
    if (!s || !s.tools) return "";
    const order = TOOL_PILLS[p.isPit ? "pit" : "hit"];
    const known = new Set(order.map(o => o[1]));
    const extra = Object.keys(s.tools).filter(k => !known.has(k) && s.tools[k] != null).map(k => [k.toUpperCase().replace(/_/g, " "), k]);
    const et = eToolsOf(p);
    const pills = order.concat(extra).filter(([, k]) => s.tools[k] != null).map(([lbl, k]) => {
      const r = et[k];
      const raw = r ? Number(r.shown) : Number(s.tools[k]);
      const g = r ? r.shown : Math.ceil(raw);   // owner rule: consensus tool grades display ceiling
      const isTool = k !== "frame" && k !== "athl" && k !== "delivery";
      const mark = (MLBP_ETOOLS_ON && isTool)
        ? `<sup style="font-size:8px;margin-left:1px;opacity:0.8;" aria-label="${r ? "eTool" : "consensus"}">${r ? "e" : "c"}</sup>` : "";
      const tip = !MLBP_ETOOLS_ON || !isTool ? ""
        : r ? `${lbl} ${g}: eTool, the consensus grade moved by his own minor-league stats, to the nearest grade (${Number(r.etool).toFixed(1)}). Consensus ${Math.ceil(Number(s.tools[k]))}, rounded up.`
          : `${lbl} ${g}: consensus grade, rounded up`;
      // Only the grade COLOUR stays inline (gradeColor is a value read off the
      // 20-80 grade); the pill shape lives on .mlbp-toolpill.
      return `<span class="mlbp-toolpill"${tip ? ` title="${esc(tip)}"` : ""}>
          <span class="mlbp-toolpill-label">${esc(lbl)}${mark}</span>
          <span class="mlbp-toolpill-val" style="color:${gradeColor(raw)};">${g}</span></span>`;
    }).join("");
    return pills ? `<div class="mlbp-toolpills">${pills}</div>` : "";
  }
  // Scouting slice (ex-PROSPX players): the latest published report blurb + the
  // 20-80 tool grades as pills. Both are conditional - a player with neither
  // renders nothing (no empty shell).
  function scoutingBlock(p) {
    const s = p.scout;
    if (!s) return "";
    let pillsHtml = scoutToolPills(p);
    if (MLBP_ETOOLS_ON && pillsHtml) {
      ensureETools();
      pillsHtml = slotHTML("scouttools", pillsHtml);
    }
    let reportHtml = "";
    const r = s.report;
    if (r && r.text) {
      // An excerpt of the publisher's report (owner answer 2026-09-25): the
      // link goes to the source's own page when one is known, otherwise the
      // source and list are named and the link goes to the publisher's list
      // page (owner answer 2026-10-01, REPEX-1 b), saying it lands on a list.
      const srcName = r.source || "Scouting report";
      const listText = r.list_page ? `View the list on ${srcName}` : `View lists on ${srcName}`;
      const srcLink = r.url
        ? ` <a class="fa-player-link" href="${esc(r.url)}" target="_blank" rel="noopener">View on ${esc(srcName)} &#8599;</a>`
        : (r.list_url && /^https:\/\//.test(String(r.list_url)))
          ? ` <a class="fa-player-link" href="${esc(r.list_url)}" target="_blank" rel="noopener" title="${esc(r.list_page ? `The page for ${r.label || "the list"}, not a player page` : `The ${srcName} prospect lists, not a player page`)}">${esc(listText)} &#8599;</a>`
          : "";
      reportHtml = `<div class="mlbp-scout-report">
        <div class="fa-sub mlbp-scout-src">${esc(srcName)}${r.label ? ` · ${esc(r.label)}` : ""}${r.date ? ` · ${esc(r.date)}` : ""}${r.truncated ? " · excerpt" : ""}</div>
        <p class="mlbp-scout-text">${esc(r.text)}${srcLink}${p.origin && p.origin.prospx ? ` <a class="fa-player-link" href="/prospx/#player=${encodeURIComponent(p.origin.prospx)}">prospect card &rarr;</a>` : ""}</p></div>`;
    }
    if (!pillsHtml && !reportHtml) return "";
    return section("scouting", "Scouting", MLBP_ETOOLS_ON ? "20-80 tools (e: eTool, c: consensus) · latest report · via PROSPX" : "consensus 20-80 tools · latest report · via PROSPX", pillsHtml + reportHtml);
  }
  // Games by position from the nightly fielding feed, joined on the card's
  // MLBAM id (a name-slug join showed one Max Muncy's line on the other's
  // page) and stamped with the feed's own date: the season label alone would
  // read as current when the feed is not.
  function positionGamesSummary(key) {
    const card = DETAIL && (DETAIL.players || {})[key];
    const mid = card && card.mlbam;
    const positions = mid != null && FIELDING && FIELDING.players && FIELDING.players[String(mid)];
    if (!positions) return "";
    const rows = Object.entries(positions)
      .map(([pos, row]) => ({
        pos,
        games: Number(row && row[0]),
        starts: row && row[1] != null ? Number(row[1]) : NaN,
        innings: row && row[2] != null ? Number(row[2]) : NaN,
      }))
      .filter(r => Number.isFinite(r.games) && r.games > 0)
      .sort((a, b) => (b.games - a.games) || (b.innings - a.innings) || a.pos.localeCompare(b.pos));
    if (!rows.length) return "";
    const season = FIELDING.season || "current";
    const asOf = FIELDING.as_of ? String(FIELDING.as_of).slice(0, 10) : "";
    return `<div class="position-usage-strip">
      <span class="position-usage-label">${esc(String(season))} games by position</span>
      ${rows.map(r => {
        const title = `${r.pos}: ${r.games} games${Number.isFinite(r.starts) ? `, ${r.starts} starts` : ""}${Number.isFinite(r.innings) ? `, ${r.innings} innings` : ""}`;
        return `<span class="position-usage-chip" title="${esc(title)}"><span>${esc(r.pos)}</span>:${esc(String(r.games))}</span>`;
      }).join("")}
      ${asOf ? `<span class="fa-sub">as of ${esc(asOf)}</span>` : ""}
    </div>`;
  }

  // ---- timeline strip (wiring W01 part 2, Q9_22b) ----------------------------
  // The player's dated MLB transactions: IL placements and activations with the
  // list and the in-season days, trades, signings with terms, options, DFA,
  // releases and arbitration salaries. One small file per player under
  // /data/mlb_events/, keyed by MLBAM id (mlb_events.py), fetched only when the
  // page shell says that directory is served: build_site writes
  // data-mlb-events="live" on #proj-rows while mlb_events.MLB_EVENTS_LIVE is True
  // and nothing otherwise, so with the flag off no request is made and the page
  // is what it was. The 5 MB card set never grows for this.
  // StatsAPI description text prints verbatim. Nothing here forecasts
  // availability: the IL playing-time adjustment failed on both sides, so the IL
  // rows are history only.
  // Rows key by the type codes of the site-pass type registry (plan 3.2):
  // data-type is the code, data-fam the family (pro, mlb, fa, trd, inj), and the
  // stylesheet colours a family from its wire token (--wire-*). The pictograms
  // are the interim set of plan 3.3; once EEPHUS_HUB.wireType (HOME_2) exists,
  // its entry for a code wins field by field (fam, ico).
  const TL_TYPES = {
    draft_sign:    { fam: "pro", ico: "px-draft",   val: "signed" },
    intl_sign:     { fam: "pro", ico: "px-intl",    val: "IFA signing" },
    callup:        { fam: "mlb", ico: "ev-promo",   val: "contract selected" },
    recall:        { fam: "mlb", ico: "ev-promo",   val: "recalled" },
    optioned:      { fam: "mlb", ico: "ev-demo",    val: "optioned" },
    dfa:           { fam: "mlb", ico: "franchise",  val: "DFA" },
    outright:      { fam: "mlb", ico: "franchise",  val: "outrighted" },
    claim:         { fam: "mlb", ico: "franchise",  val: "claimed" },
    release:       { fam: "mlb", ico: "franchise",  val: "released" },
    retire:        { fam: "mlb", ico: "franchise",  val: "retired" },
    suspend:       { fam: "mlb", ico: "franchise",  val: "suspended" },
    rule5:         { fam: "mlb", ico: "franchise",  val: "Rule 5 pick" },
    award:         { fam: "mlb", ico: "hof",        val: "award" },
    fa_sign:       { fam: "fa",  ico: "ev-signing", val: "MLB deal" },
    minor_deal:    { fam: "fa",  ico: "ev-signing", val: "MiLB deal" },
    opt_declined:  { fam: "fa",  ico: "ev-signing", val: "option declined" },
    opt_exercised: { fam: "fa",  ico: "ev-signing", val: "option exercised" },
    qo:            { fam: "fa",  ico: "ev-signing", val: "QO offered" },
    arb_salary:    { fam: "fa",  ico: "ev-signing", val: "arbitration" },
    trade:         { fam: "trd", ico: "ev-trade",   val: "trade" },
    il_place:      { fam: "inj", ico: "ev-il",      val: "IL" },
    il_return:     { fam: "inj", ico: "ev-il",      val: "activated" },
  };
  // Hidden prefix (plan 3.1) and the key's label, per family.
  const TL_FAM = {
    pro: ["Prospect", "Prospects"], mlb: ["MLB", "MLB"], fa: ["Free agency", "Free agency"],
    trd: ["Trade", "Trades"], inj: ["Injury", "Injuries"],
  };
  // The bigger marks on the Moves lane: a change of club, contract or status.
  const TL_MAJOR = new Set(["trade", "fa_sign", "minor_deal", "draft_sign", "intl_sign", "dfa",
    "claim", "release", "retire", "rule5", "suspend", "qo", "opt_declined", "opt_exercised", "award"]);
  // Seasons shown open, newest first, until at least this many rows; the rest
  // sit behind one disclosure.
  const TL_OPEN_ROWS = 8;
  const TL_MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const EVENTS = Object.create(null);         // mlbam -> payload | {missing} | {failed}
  const EVENTS_LOADING = Object.create(null);
  let EVENTS_ON = null;
  let TL_SPRITE = null;

  function eventsLive() {
    if (EVENTS_ON !== null) return EVENTS_ON;
    let on = false;
    try {
      const el = document.getElementById("proj-rows");
      on = !!(el && el.getAttribute("data-mlb-events") === "live");
    } catch (e) { on = false; }
    EVENTS_ON = on;
    return on;
  }
  function tlType(code) {
    const base = TL_TYPES[code] || { fam: "mlb", ico: "franchise", val: "" };
    const H = typeof window !== "undefined" ? window.EEPHUS_HUB : null;
    const w = H && H.wireType && H.wireType[code];
    if (!w || typeof w !== "object") return base;
    const fam = String(w.fam || "").toLowerCase();
    return { fam: TL_FAM[fam] ? fam : base.fam, ico: w.ico ? String(w.ico) : base.ico, val: base.val };
  }
  function tlSprite() {
    if (TL_SPRITE) return TL_SPRITE;
    let h = null;
    try {
      const u = document.querySelector('use[href*="/assets/eephus-icons.svg"]');
      h = u && u.getAttribute ? u.getAttribute("href") : null;
    } catch (e) { h = null; }
    TL_SPRITE = h ? String(h).split("#")[0] : "/assets/eephus-icons.svg";
    return TL_SPRITE;
  }
  // The 12 px pictogram over the shared sprite (build_site._ico's 12 px form).
  function tlIco(ico) {
    return `<svg class="ico" width="12" height="12" viewBox="2 2 12 12" aria-hidden="true" focusable="false">`
      + `<use href="${esc(tlSprite())}#i-${esc(ico)}" width="16" height="16"/></svg>`;
  }
  // A club mention: the hub's one club link for one of the 30 clubs, nothing
  // for a minor-league affiliate or an unknown id (never a guessed club).
  function tlClub(x) {
    const H = typeof window !== "undefined" ? window.EEPHUS_HUB : null;
    if (x == null || x === "" || !H || !H.club) return "";
    const c = H.club(x);
    if (!c) return "";
    return H.clubLinkHTML ? H.clubLinkHTML(c.code) : esc(c.code);
  }
  const tlIso = s => /^\d{4}-\d{2}-\d{2}/.test(String(s || ""));
  function tlDay(s, withYear) {
    if (!tlIso(s)) return "";
    const y = s.slice(0, 4), m = Number(s.slice(5, 7)), d = Number(s.slice(8, 10));
    return `${TL_MON[m - 1] || ""} ${d}${withYear ? `, ${y}` : ""}`;
  }
  const tlMs = s => Date.UTC(Number(s.slice(0, 4)), Number(s.slice(5, 7)) - 1, Number(s.slice(8, 10)));
  const tlSortKey = r => (tlIso(r.date) ? String(r.date).slice(0, 10) : `${r.season || 0}-00-00`);
  const tlSeason = r => (tlIso(r.date) ? Number(String(r.date).slice(0, 4)) : Number(r.season) || null);
  const tlPlural = (n, w) => `${n} ${w}${n === 1 ? "" : "s"}`;
  // A placement with no activation on file whose season window (to Oct 1) runs
  // past the feed's last day: the builder's day count closes it at the window's
  // end, a date the feed has not reached, so the page prints the stint as open
  // through that day instead of a count of days not yet played.
  const tlOpen = (r, through) => r.type === "il_place" && !tlIso(r.il_end) && tlIso(r.date)
    && tlIso(through) && `${String(r.date).slice(0, 4)}-10-01` > String(through).slice(0, 10);

  function ensureEvents(key) {
    if (!eventsLive()) return;
    const card = DETAIL && (DETAIL.players || {})[key];
    const mid = card && card.mlbam;
    if (mid == null || EVENTS[mid] || EVENTS_LOADING[mid]) return;
    EVENTS_LOADING[mid] = true;
    const landed = d => {
      EVENTS[mid] = d || { missing: true };
      EVENTS_LOADING[mid] = false;
      patchSlot("timeline", key, timelineBlock(key));
    };
    fetch("/data/mlb_events/" + encodeURIComponent(String(mid)) + ".json", { cache: "no-cache" })
      .then(r => {
        if (r.status === 404) return { missing: true };
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then(landed)
      .catch(() => landed({ failed: true }));
  }

  function tlValue(r, t, through) {
    const v = [];
    switch (r.type) {
      case "trade": {
        const a = tlClub(r.from), b = tlClub(r.to);
        v.push(a && b ? `${a} &rarr; ${b}` : (a || b || t.val));
        break;
      }
      case "claim": {
        const a = tlClub(r.from);
        v.push(a ? `claimed from ${a}` : t.val);
        break;
      }
      case "il_place":
        v.push(esc(r.il || t.val));
        if (tlOpen(r, through)) v.push(`open through ${tlDay(String(through).slice(0, 10))}`);
        else if (r.il_days != null && Number.isFinite(Number(r.il_days)))
          v.push(tlPlural(Number(r.il_days), "in-season day"));
        break;
      case "fa_sign": {
        const yrs = Number(r.years), g = r.guarantee_usd;
        if (r.mlb_deal === false) v.push("MiLB deal");
        else if (Number.isFinite(yrs) && yrs > 0 && g != null) v.push(`${yrs}y/${money(g)}`);
        else v.push(t.val);
        const to = tlClub(r.to_team);
        if (to) v.push(to);
        break;
      }
      case "opt_declined":
      case "opt_exercised":
        v.push(t.val + (r.option_price_usd != null ? ` ${money(r.option_price_usd)}` : ""));
        break;
      case "arb_salary": {
        v.push(money(r.salary_usd) + (r.arb_year ? ` · arb-${esc(String(r.arb_year))}` : ""));
        const c = tlClub(r.club);
        if (c) v.push(c);
        break;
      }
      default:
        if (t.val) v.push(esc(t.val));
    }
    return v.filter(Boolean).join(" · ");
  }
  // Rows from a source with no StatsAPI text (the FA ledger, arbitration
  // salaries) say what the record is; StatsAPI rows print their own text.
  function tlText(r) {
    if (r.desc) return esc(r.desc);
    switch (r.type) {
      case "arb_salary": return `Arbitration-eligible salary, ${esc(String(r.season || ""))}`;
      case "fa_sign": return "Free-agent signing";
      case "opt_declined": return "Option declined";
      case "opt_exercised": return "Option exercised";
      case "qo": return "Qualifying offer";
      default: return esc((TL_TYPES[r.type] || {}).val || r.type || "");
    }
  }
  function tlRow(r, through) {
    const t = tlType(r.type);
    const when = tlIso(r.date)
      ? `<time class="mlbp-tl-date" datetime="${esc(String(r.date).slice(0, 10))}">${tlDay(String(r.date))}</time>`
      : `<span class="mlbp-tl-date">season</span>`;
    const val = tlValue(r, t, through);
    return `<li class="mlbp-tl-row" data-fam="${t.fam}" data-type="${esc(r.type)}">${when}`
      + `<span class="mlbp-tl-mark">${tlIco(t.ico)}<span class="visually-hidden">${TL_FAM[t.fam][0]}:</span></span>`
      + `<span class="mlbp-tl-text">${tlText(r)}</span>`
      + (val ? `<span class="mlbp-tl-val">${val}</span>` : "") + `</li>`;
  }
  function tlSeasonHTML(y, rows, ilSeasons, through) {
    const il = ilSeasons && ilSeasons[String(y)];
    const open = rows.filter(r => tlOpen(r, through)).length;
    const ilNote = il && il[1] > 0
      ? ` <span class="fa-sub">${tlPlural(Number(il[1]), "IL stint")}, `
        + (open ? `${open} open` : tlPlural(Number(il[0]), "in-season day")) + `</span>` : "";
    return `<div class="mlbp-tl-season"><div class="mlbp-tl-year">${y == null ? "" : esc(String(y))}${ilNote}</div>`
      + `<ol class="mlbp-tl-rows">${rows.map(r => tlRow(r, through)).join("")}</ol></div>`;
  }
  function tlList(ev, rows) {
    const sorted = rows.slice().sort((a, b) => {
      const ka = tlSortKey(a), kb = tlSortKey(b);
      return ka < kb ? 1 : ka > kb ? -1 : 0;
    });
    const seasons = [];
    for (const r of sorted) {
      const y = tlSeason(r);
      const last = seasons[seasons.length - 1];
      if (last && last.y === y) last.rows.push(r);
      else seasons.push({ y, rows: [r] });
    }
    let shown = 0, cut = seasons.length;
    for (let i = 0; i < seasons.length; i++) {
      if (shown >= TL_OPEN_ROWS) { cut = i; break; }
      shown += seasons[i].rows.length;
    }
    const block = list => list.map(s => tlSeasonHTML(s.y, s.rows, ev.il_seasons, ev.through)).join("");
    const rest = seasons.slice(cut);
    const nRest = rest.reduce((a, s) => a + s.rows.length, 0);
    const restYears = rest.length ? `${rest[rest.length - 1].y}-${rest[0].y}` : "";
    return block(seasons.slice(0, cut))
      + (rest.length
        ? `<details class="mlbp-tl-more"><summary>${tlPlural(nRest, "earlier move")} <span class="fa-sub">${esc(restYears)}</span></summary>${block(rest)}</details>`
        : "");
  }
  // The strip: one track of moves and one of IL stints on a shared year axis.
  // A visual summary only (aria-hidden); the list below carries every row.
  function tlStrip(ev, rows) {
    const dated = rows.filter(r => tlIso(r.date)).map(r => Object.assign({}, r, { date: String(r.date).slice(0, 10) }));
    if (!dated.length) return "";
    let first = dated[0].date, last = dated[0].date;
    dated.forEach(r => { if (r.date < first) first = r.date; if (r.date > last) last = r.date; });
    if (tlIso(ev.through) && String(ev.through).slice(0, 10) > last) last = String(ev.through).slice(0, 10);
    const y0 = Number(first.slice(0, 4)), y1 = Number(last.slice(0, 4));
    const lo = Date.UTC(y0, 0, 1), hi = Date.UTC(y1 + 1, 0, 1);
    const pct = ms => Math.max(0, Math.min(100, (ms - lo) / (hi - lo) * 100));
    const at = ms => pct(ms).toFixed(2) + "%";
    const span = y1 - y0 + 1;
    const step = span <= 7 ? 1 : span <= 14 ? 2 : 5;
    let grid = "", axis = "";
    for (let y = y0; y <= y1; y++) {
      const x = at(Date.UTC(y, 0, 1));
      if (y > y0) grid += `<span class="mlbp-tl-yr" style="left:${x}"></span>`;
      if ((y - y0) % step === 0) axis += `<span style="left:${x}">${y}</span>`;
    }
    const pins = dated.filter(r => r.type !== "il_place" && r.type !== "il_return").map(r => {
      const t = tlType(r.type);
      return `<span class="mlbp-tl-pin${TL_MAJOR.has(r.type) ? " is-major" : ""}" data-fam="${t.fam}" data-type="${esc(r.type)}"`
        + ` style="left:${at(tlMs(r.date))}" title="${esc(tlDay(r.date, true))}: ${esc(r.desc || t.val || r.type)}"></span>`;
    }).join("");
    const thru = tlIso(ev.through) ? String(ev.through).slice(0, 10) : last;
    // A bar runs from the placement to its activation, cut at the season
    // window's end (Oct 1) as the in-season day count is, and never past the
    // feed's last day: a stint closed only by a placement seasons later is not
    // drawn as years on the list.
    const bars = dated.filter(r => r.type === "il_place").map(r => {
      const y = r.date.slice(0, 4);
      const seasonEnd = `${y}-10-01`;
      const back = tlIso(r.il_end) && String(r.il_end).slice(0, 4) === y ? String(r.il_end).slice(0, 10) : null;
      let end = [back || seasonEnd, seasonEnd, thru].sort()[0];
      if (end < r.date) end = r.date;
      const x0 = pct(tlMs(r.date)), x1 = pct(tlMs(end));
      const t = tlType(r.type);
      const title = `${r.il || "IL"}, ${tlDay(r.date, true)}${back ? ` to ${tlDay(back, true)}` : ""}`;
      return `<span class="mlbp-tl-bar" data-fam="${t.fam}" data-type="il_place" style="left:${x0.toFixed(2)}%;width:${Math.max(0.4, x1 - x0).toFixed(2)}%" title="${esc(title)}"></span>`;
    }).join("");
    const fams = [];
    rows.forEach(r => { const f = tlType(r.type).fam; if (!fams.includes(f)) fams.push(f); });
    const order = ["trd", "fa", "mlb", "inj", "pro"];
    const key = order.filter(f => fams.includes(f)).map(f => {
      // The family mark of the MLB News registry (EEPHUS_HUB.wireFamily, HOME_2)
      // when the hub is loaded; the interim marks otherwise.
      const H = typeof window !== "undefined" ? window.EEPHUS_HUB : null;
      const wf = H && H.wireFamily && H.wireFamily[f];
      const ico = (wf && wf.mark) || { trd: "ev-trade", fa: "ev-signing", mlb: "franchise", inj: "ev-il", pro: "prospx" }[f];
      return `<span class="mlbp-tl-key-item" data-fam="${f}">${tlIco(ico)}${TL_FAM[f][1]}</span>`;
    }).join("");
    return `<div class="mlbp-tl-strip" aria-hidden="true">`
      + `<span class="mlbp-tl-lane-label">Moves</span><div class="mlbp-tl-track">${grid}${pins}</div>`
      + `<span class="mlbp-tl-lane-label">IL</span><div class="mlbp-tl-track">${grid}${bars}</div>`
      + `<span></span><div class="mlbp-tl-axis">${axis}</div></div>`
      + (key ? `<div class="mlbp-tl-key">${key}</div>` : "");
  }
  function timelineBlock(key) {
    if (!eventsLive()) return "";
    const card = DETAIL && (DETAIL.players || {})[key];
    const ev = card && card.mlbam != null ? EVENTS[card.mlbam] : null;
    if (!ev || ev.missing) return "";
    if (ev.failed)
      return section("timeline", "Timeline", "", `<div class="fa-note">Timeline did not load.</div>`);
    const rows = (ev.rows || []).filter(r => r && r.type);
    const sub = tlIso(ev.through) ? `MLB moves through ${tlDay(String(ev.through).slice(0, 10), true)}` : "";
    if (!rows.length)
      return section("timeline", "Timeline", sub, `<div class="fa-note">No MLB transactions on file.</div>`);
    const hasIl = rows.some(r => r.type === "il_place");
    const foot = [
      "Descriptions are quoted from MLB StatsAPI",
      hasIl ? "in-season days count each IL stint inside Apr 1 to Oct 1, ended by the next IL move" : "",
      rows.some(r => r.type === "arb_salary") ? "arbitration salaries are dated by season" : "",
    ].filter(Boolean).join("; ") + ".";
    return section("timeline", "Timeline", sub,
      `<div class="mlbp-tl">${tlStrip(ev, rows)}${tlList(ev, rows)}<div class="fa-note mlbp-tl-foot">${foot}</div></div>`);
  }

  // Tabs are questions, not sources. Hitter: Overview, Hitting, Defense, Value,
  // Projection & Contract, Scouting, Discussion. Pitcher: no Defense, Pitching
  // in place of Hitting. Two-way: both, Defense only with fielded innings. A tab
  // renders only when its panel has content (an empty async slot does not
  // count). Every panel stays in the DOM, hidden when inactive, so async fills
  // can land in an unopened tab. The active tab is state.ptab when that panel
  // exists, else the first.
  function mlbpTabs(panels, key) {
    const nonEmpty = (h) => !!(h && h.replace(/\s+/g, "").length);
    const shown = panels.filter(pan => nonEmpty(pan.content != null ? pan.content : pan.html));
    // Discussion (per-player thread). Gated on the forum layer being loaded so a
    // build without it never leaves an empty shell; the layer itself paints a
    // quiet "No comments yet" state when Supabase config is blank.
    if (window.EephusUI && typeof window.EephusUI.mountForum === "function")
      shown.push({ id: "discussion", label: "Discussion", html: '<div id="eph-forum-mount"></div>' });
    if (!shown.length) return "";
    const want = (state.ptab && PTAB_FOR === key && shown.some(pan => pan.id === state.ptab)) ? state.ptab : shown[0].id;
    // aria-selected is the ONLY state: the stylesheet draws the selected and
    // unselected tabs off it (.mlbp-tab[aria-selected="true"]).
    const strip = shown.length > 1
      ? `<div class="mlbp-tabs" role="tablist">${shown.map(pan => `<button type="button" class="chip mlbp-tab" data-mlbp-tab="${pan.id}" role="tab" aria-selected="${pan.id === want}">${pan.label}</button>`).join("")}</div>`
      : "";
    const body = shown.map(pan => `<div class="mlbp-tabpanel" data-mlbp-panel="${pan.id}" role="tabpanel"${pan.id === want ? "" : " hidden"}>${pan.html}</div>`).join("");
    return strip + body;
  }

  function bindMlbpTabs(root, p, key) {
    // Mount the forum thread the first time the Discussion tab is opened (the
    // account/forum layer loads it only while that tab is active - the prospect
    // page uses the same lazy pattern). No-op without the layer.
    let forumMounted = false;
    const maybeMountForum = (id) => {
      if (id !== "discussion" || forumMounted) return;
      if (!(window.EephusUI && window.EephusUI.mountForum)) return;
      forumMounted = true;
      try { window.EephusUI.mountForum("mlb", key, { name: p.name, player_name: p.name, key: key }); }
      catch (e) { /* non-fatal */ }
    };
    const active = root.querySelector("[data-mlbp-panel]:not([hidden])");
    if (active) maybeMountForum(active.getAttribute("data-mlbp-panel"));
    const activate = (id) => {
      const panes = root.querySelectorAll("[data-mlbp-panel]");
      let found = false;
      panes.forEach((pane) => { if (pane.getAttribute("data-mlbp-panel") === id) found = true; });
      if (!found) return false;
      root.querySelectorAll("[data-mlbp-tab]").forEach((b) => {
        b.setAttribute("aria-selected", b.getAttribute("data-mlbp-tab") === id ? "true" : "false");
      });
      panes.forEach((pane) => {
        if (pane.getAttribute("data-mlbp-panel") === id) pane.removeAttribute("hidden");
        else pane.setAttribute("hidden", "hidden");
      });
      // The tab is state, kept in the URL (replaceState, so no hashchange fires).
      state.ptab = id;
      PTAB_FOR = key;
      syncToURL();
      maybeMountForum(id);
      return true;
    };
    root.querySelectorAll("[data-mlbp-tab]").forEach((t) => t.addEventListener("click", () => {
      activate(t.getAttribute("data-mlbp-tab"));
    }));
    // Overview lenses open the tab that owns their number.
    root.querySelectorAll("[data-mlbp-goto]").forEach((b) => b.addEventListener("click", () => {
      if (!activate(b.getAttribute("data-mlbp-goto"))) return;
      const strip = root.querySelector(".mlbp-tabs");
      if (strip && strip.scrollIntoView) strip.scrollIntoView({ block: "nearest" });
    }));
  }

  function pageFoot(p) {
    const sk = p.skills || {};
    return [
      `${term("fa_projection_engine", "Projection engine")} proj_lgbm_v1, bands = its P10 / P90 quantile heads`,
      `Statcast percentiles ${SAVANT_POOL}`,
      p.swingPlus != null ? "Swing+ (MLB bat tracking 2024+)" : "",
      p.aaaStuffPlus != null ? "aStuff+: in-house AAA pitch model, latest tracked AAA season" : "",
      (p.origin || {}).aaaHit ? "Statcast (tracked parks): Baseball Savant minors, latest 100+ PA season" : "",
      sk.def ? "Fielding, framing and positional runs: FanGraphs, via MLB StatsAPI" : "",
      sk.br ? "Baserunning: eBR counted here from MLB play-by-play; BsR FanGraphs via MLB StatsAPI; BRV and sprint speed Baseball Savant" : "",
    ].filter(Boolean).join(" · ");
  }

  function renderPlayer(key) {
    const root = document.getElementById("proj-rows");
    const bar = document.getElementById("proj-filters");
    const banner = document.getElementById("proj-banner");
    if (banner) banner.innerHTML = "";
    if (bar) bar.innerHTML = `<a class="chip" href="#" id="mlbp-back">← back to projections</a>`;
    const back = document.getElementById("mlbp-back");
    if (back) back.onclick = (e) => { e.preventDefault(); state.player = null; syncToURL(); render(); };
    PAINTED_PLAYER = null;
    if (!(DETAIL && (DETAIL.players || {})[key]) && !(DETAIL && DETAIL.all)) {
      root.innerHTML = pxState("loading", "Loading player.");
      loadCard(key);
      return;
    }
    const p = (DETAIL.players || {})[key];
    if (!p) {
      root.innerHTML = `<div class="state-message">No detail for "${esc(key)}". <a href="#" onclick="location.hash='';return false;">Back</a>.</div>`;
      return;
    }
    // A tab chosen on another player does not carry over.
    if (PTAB_FOR !== key) { state.ptab = null; PTAB_FOR = key; }
    const hitSide = !p.isPit || !!p.twoWay;
    const pitSide = !!p.isPit || !!p.twoWay;
    // .mlbp-headshot is 96x96 (site.css), same box fa.js asks for. A 'none'
    // context returns null: no img at all rather than a known-404 request.
    const heroShot = headshotURL(p.mlbam, 96);
    const photo = heroShot
      ? `<img class="mlbp-headshot" src="${heroShot}" alt="" onerror="this.style.visibility='hidden'">` : "";
    // ASK C: where the salary path knows the window end, the card states THAT
    // and not "arb / pre-arb". `remaining_control_years` (debut+6) keeps being
    // emitted for the rank gate but no longer contradicts it on a surface.
    const _pr = p.proj || {};
    const _cThru = _pr.ctrlThru != null ? _pr.ctrlThru
      : (Math.max(_pr.thru || 0, _pr.salThru || 0) || null);
    const _cOpen = _pr.ctrlThru != null ? !!_pr.ctrlOpen : !!_pr.salTrunc;
    const _cWord = _cThru == null ? ""
      : _cOpen ? `club control thru at least ${_cThru}` : `club control thru ${_cThru}`;
    const contract = _pr.thru
      ? `signed thru ${_pr.thru}${_pr.aav ? ` · ${money(_pr.aav)}/y` : ""}`
        + (_cThru && _cThru > _pr.thru ? ` · ${_cWord}` : "")
      : _cThru
      ? _cWord
      : (p.fa ? `free agent${p.fa.type ? ` · ${esc(p.fa.type)}` : ""}` : "arb / pre-arb");
    // Prospect origin block (ex-PROSPX graduates, wiring W06): what PROSPX
    // said before he arrived. The one grade it prints is eFV at debut
    // (the backgrade's xfv_grade_at_debut) to the nearest point, never the
    // consensus arc (owner answer Q-E4), beside the debut date and the club
    // he debuted with; a hitter's final tracked-park Statcast line sits under
    // it, the batter twin of the aStuff+ tile. One player's own numbers only.
    const org = p.origin;
    const devOrg = org && org.devOrg
      ? (franchiseHref(org.devOrg)
        ? ` with <a class="fa-player-link" href="${esc(franchiseHref(org.devOrg))}">${esc(org.devOrg)}</a>`
        : ` with ${esc(org.devOrg)}`) : "";
    const originLine = (org && org.prospx)
      ? `<div class="fa-sub mlbp-origin-line"><a class="fa-player-link" href="/prospx/#player=${encodeURIComponent(org.prospx)}">ex-PROSPX prospect &rarr;</a>${org.efvDebut != null ? `<span>· ${term("xfv", "eFV")} at debut ${Math.round(org.efvDebut)}</span>` : ""}${org.debut ? `<span>· debuted ${esc(org.debut)}${devOrg}</span>` : ""}</div>${aaaHitLine(org.aaaHit)}`
      : "";
    const ov = overviewPanel(p, key);
    const hit = hitSide ? hittingPanel(p) : null;
    const pit = pitSide ? pitchingPanel(p) : null;
    const panels = [
      { id: "overview", label: "Overview", html: ov.html, content: ov.content },
      hit ? { id: "hitting", label: "Hitting", html: hit.html, content: hit.content } : null,
      pit ? { id: "pitching", label: "Pitching", html: pit.html, content: pit.content } : null,
      hitSide ? { id: "defense", label: "Defense", html: defensePanel(p) } : null,
      { id: "value", label: "Value", html: valuePanel(p) },
      { id: "projection", label: "Projection &amp; Contract", html: projectionPanel(p) },
      { id: "scouting", label: "Scouting", html: scoutingBlock(p) },
    ].filter(Boolean);
    root.innerHTML = `<div class="mlbp-page">
      <div class="mlbp-slot" id="mlbp-hub" data-mlbp-slot="hub"></div>
      <div class="mlbp-hero">
        ${photo}
        <div class="mlbp-hero-main">
          <div class="mlbp-name">${clubA(p.team, teamLogo(p.team), { mark: true })}<h2>${esc(p.name || key)}</h2></div>
          <div class="fa-sub">${esc(p.pos || "")}${p.age != null ? ` · age ${Math.floor(p.age)}` : ""}${p.team ? ` · ${clubA(p.team, esc(p.team), { cls: "fa-player-link" })}` : " · FA"} · ${contract}</div>
          ${originLine}
          <div class="mlbp-hero-actions"><button class="chip egfx-chip" id="mlbp-gfx" title="Shareable graphic"><span class="egfx-chip-glyph" aria-hidden="true">${window.EephusIco ? window.EephusIco("gfx", 12) : ""}</span>Generate GFX</button>${(p.proj && surOf(p.proj) != null) ? `<a class="chip" href="/trademachine/#tm=mlb:${encodeURIComponent(key)}">${window.EephusIco ? window.EephusIco("trademachine", 12) : ""} Trade Machine</a>` : ""}</div>
        </div>
        <div class="mlbp-tiles">${heroTiles(p)}${salaryStripHtml(p.proj, { cls: "mlbp-sp" })}</div>
      </div>
      ${mlbpTabs(panels, key)}
      <div class="fa-note mlbp-page-foot">${pageFoot(p)}</div>
    </div>`;
    bindMlbpTabs(root, p, key);
    PAINTED_PLAYER = key;
    if (window.EEPHUS_GL) window.EEPHUS_GL.wire(root);
    // Async fills run AFTER the first paint and patch their own slot, so none
    // of them re-renders the page under the reader.
    ensureFielding();
    ensureEvents(key);
    if (hitSide) ensureSwingDelta();
    if (hitSide) ensureStatcastCatcher();
    // Only client-fetch the pitching leaderboards when the skills block was not
    // baked into the payload (older builds); the baked block renders directly.
    if (pitSide && !(p.skills && p.skills.pitch)) ensurePitchingStats();
    // Hub strip (cross-module identity). The row is the one
    // mlb_player_export._export_links writes for this card, built from the
    // card itself, so the page never downloads the 1.9 MB identity map.
    if (window.EEPHUS_HUB) {
      const el = document.getElementById("mlbp-hub");
      const row = { key, mlbam: p.mlbam, fa: !!p.fa, proj: true,
                    prospx: (p.origin || {}).prospx || null };
      if (el && window.EEPHUS_HUB.stripHTML) el.innerHTML = window.EEPHUS_HUB.stripHTML(row, "mlb");
      const btn = document.getElementById("mlbp-gfx");
      if (btn) btn.onclick = () => shareMlbCard(p);
    }
  }

  // One card: its shard, or the whole set when the shard is missing. A card
  // that lands before the board renders on the board's two scalars it carries.
  function cardFailed(key) {
    const root = document.getElementById("proj-rows");
    if (!root || state.player !== key) return;
    root.innerHTML = pxState("failed", `Player card did not load. The nightly build may be writing it. <button class="chip" id="mlbp-detail-retry" type="button">Retry</button>`);
    const retry = document.getElementById("mlbp-detail-retry");
    if (retry) retry.onclick = () => { if (state.player) renderPlayer(state.player); };
  }
  function cardLanded(key, frame) {
    if (!DATA && frame && frame.first_season != null) {
      DATA = { first_season: frame.first_season, horizon: frame.horizon,
               generated_at: frame.generated_at, vets: [], prospects: [], partial: true };
    }
    if (state.player === key && DATA) renderPlayer(key);
  }
  function loadAllCards(key) {
    if (DETAIL_ALL_LOADING) return;
    DETAIL_ALL_LOADING = true;
    fetch("/data/mlb_player_detail.json", { cache: "no-cache" })
      .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
      .then(d => {
        DETAIL = { players: Object.assign((d && d.players) || {}, (DETAIL && DETAIL.players) || {}), all: true };
        cardLanded(state.player || key, d);
      })
      .catch(() => { DETAIL_ALL_LOADING = false; cardFailed(state.player || key); });
  }
  function loadCard(key) {
    if (!key || CARD_LOADING[key] || (DETAIL && DETAIL.players[key])) return;
    CARD_LOADING[key] = true;
    fetch(`/data/mlb_player_detail/${encodeURIComponent(key)}.json`, { cache: "no-cache" })
      .then(r => {
        if (r.status === 404) return null;
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then(d => {
        if (!d || !d.player) { loadAllCards(key); return; }
        DETAIL = DETAIL || { players: {} };
        DETAIL.players[key] = d.player;
        cardLanded(key, d);
      })
      .catch(() => { CARD_LOADING[key] = false; cardFailed(key); });
  }

  // One-subject card exports go through EEPHUS_HUB.openCard (the shared
  // wrapper - DE-DUP 2026-07-23; it prefers the GFX modal, falls back to the
  // direct shareCard download).

  // Board spec for the Generate GFX modal: the league projection board as a
  // column leaderboard (projected window WAR on the fWAR training label, contract surplus).
  //
  // THE P10-P90 TOTAL RANGE COLUMN IS GONE (2026-09-11). warTotalP10Comon/P90Comon
  // (named warTotalP10/P90 before RVA09) are sums of per-season quantiles
  // (proj_export sums p10_arr), the F-01 defect
  // the on-site board already dropped: a sum of P10s is not the P10 of the
  // total. The graphic kept printing it after the board stopped.
  function _projBoardSpec(top) {
    // Same HORIZON-windowed total the on-site board shows and sorts by
    // (warShown), so the shared graphic never disagrees with the board row.
    const war = m => warShown(m);
    const rows = top.map((m, i) => {
      const cells = [
        { t: i + 1 },
        { t: m.name, sub: [m.pos, m.team].filter(Boolean).join(" · ") || undefined },
        { t: war(m) != null ? fmtWar(war(m)) : "-", c: "accent" },
      ];
      const s = (surOf(m) != null) ? surOf(m) : (m.surplus != null ? m.surplus : null);
      cells.push(s != null ? { t: money(s), c: s >= 0 ? "pos" : "neg" } : { t: "-" });
      return { cells };
    });
    return {
      kind: "board", module: "MLB Projections", accentToken: "--accent-cyan",
      title: `MLB Projections · ${DATA.horizon}-Year Projected WAR Leaders`,
      subtitle: `${DATA.n_vets} veterans + ${DATA.n_prospects} prospects · seasons ${DATA.first_season}-${DATA.first_season + DATA.horizon - 1}`,
      url: "eephus.io/projections", filenameBase: "eephus-projections-board",
      caption: `Projected WAR (fWAR basis) on the expected path · prospects join at their PROSPX ETA · surplus is priced over each player's club control window, unsigned seasons through ${DATA.first_season + DATA.horizon - 1} at most`,
      board: { defaultCount: 25, counts: [10, 25, 50], columns: [
        { label: "#", frac: 0.05 },
        { label: "Player", frac: 0.52 },
        { label: `Proj ${DATA.horizon}y WAR`, frac: 0.23 },
        { label: "Surplus", frac: 0.20, wideOnly: true },
      ], rows },
    };
  }

  // Board spec for the Generate GFX modal when the Team Outlook tab is active,
  // so the graphic tracks the menu you're viewing (the Players tab exports
  // _projBoardSpec; this exports the team roll-up board instead).
  function _teamOutlookBoardSpec(rows) {
    const hasFarm = rows.some(r => r.farm);
    const hasControl = rows.some(r => r.lockedPct != null);
    const brows = rows.map((r, i) => {
      const f = r.farm || {};
      const w = Math.round(r.wins);
      const cells = [
        { t: i + 1 },
        { t: r.team },
        { t: r.war != null ? r.war.toFixed(1) : "-", c: "accent" },
        { t: `${w}-${162 - w}` },
      ];
      if (hasControl) {
        const pct = r.lockedPct != null ? Math.round(r.lockedPct * 100) : null;
        const cell = { t: pct == null ? "-" : `${pct}%` };
        if (pct != null) { if (pct >= 75) cell.c = "pos"; else if (pct <= 45) cell.c = "neg"; }
        cells.push(cell);
      }
      cells.push(f.farmRank != null ? { t: `#${f.farmRank}` } : { t: "-" });
      cells.push(f.farmSurplusMM != null
        ? { t: `$${Math.round(f.farmSurplusMM)}M`, c: f.farmSurplusMM >= 0 ? "pos" : "neg" }
        : { t: "-" });
      return { cells };
    });
    const cols = [
      { label: "#", frac: 0.06 },
      { label: "Team", frac: hasControl ? 0.26 : 0.30 },
      { label: "Roster WAR", frac: 0.16 },
      { label: "Proj W-L", frac: 0.16 },
    ];
    if (hasControl) cols.push({ label: "Core control", frac: 0.14 });
    cols.push({ label: "Farm", frac: 0.11, wideOnly: true });
    cols.push({ label: "Farm surplus", frac: 0.13, wideOnly: true });
    return {
      kind: "board", module: "MLB Projections", accentToken: "--accent-cyan",
      title: "MLB Projections · Team Outlook",
      subtitle: `${DATA.first_season} projected roster WAR (fWAR basis) → projected wins${hasControl ? " · core control" : ""} · ${rows.length} teams`,
      url: "eephus.io/projections", filenameBase: "eephus-projections-team-outlook",
      caption: "Projected roster WAR (fWAR basis) at the 47.7 replacement baseline · league-recentered"
        + (hasControl ? " · core control = share of projected WAR under contract or an age proxy" : "")
        + (hasFarm ? " · farm rank + surplus from the PROSPX org models" : ""),
      board: { defaultCount: 30, counts: [10, 30], columns: cols, rows: brows },
    };
  }

  // Unified share card - declarative since GFX slice 4: this builder now only
  // maps the detail payload's DATA (display-formatted with this module's own
  // fmtWar/money rules) onto the shared "player-projection" template;
  // EEPHUS_HUB.templates owns the tile/section layout. Data priorities are
  // unchanged: projection band + surplus + Swing+ up top, Statcast
  // percentiles and (pitchers) arsenal as the body sections.
  function shareMlbCard(p) {
    const first = DATA.first_season;
    const war = (p.proj && p.proj.war) || [];
    window.EEPHUS_HUB.openCard({
      template: "player-projection",
      data: {
        warYears: war.length,
        warTotal: (p.proj && p.proj.warTotal != null) ? fmtWar(p.proj.warTotal) : null,
        surplus: (p.proj && surOf(p.proj) != null)
          ? { value: money(surOf(p.proj)), neg: !(surOf(p.proj) >= 0) } : null,
        swingPlus: p.swingPlus != null ? String(Math.round(p.swingPlus)) : null,
        aaaStuffPlus: p.aaaStuffPlus != null ? String(Math.round(p.aaaStuffPlus)) : null,
        projAav: (p.fa && p.fa.projAav != null) ? money(p.fa.projAav) : null,
        firstSeason: first,
        lastSeason: first + (war.length - 1),
        warRows: war.map((w, t) => ({ season: String(first + t), war: fmtWar(w),
          band: (p.proj.warP10 || [])[t] != null
            ? `${fmtWar(p.proj.warP10[t])}-${fmtWar(p.proj.warP90[t])}` : null })),
        // arsenal is pitcher-gated HERE (not in the template) so a stray
        // arsenal field on a hitter payload still falls through to Statcast,
        // exactly like the pre-template builder.
        arsenal: (p.isPit && p.arsenal) ? p.arsenal.map(a => ({ pitch: a.pitch || "?",
          usageWhiff: `${a.usage != null ? a.usage.toFixed(0) + "%" : "-"} / ${a.whiff != null ? a.whiff.toFixed(0) + "%" : "-"}` })) : [],
        statcast: (p.sc && p.sc.metrics && p.sc.metrics.length)
          ? { season: p.sc.season, metrics: p.sc.metrics } : null,
      },
      module: "MLB Projections",
      accentToken: "--accent-cyan",
      name: p.name || p.key,
      meta: `${p.pos || ""}${p.age != null ? ` · age ${Math.floor(p.age)}` : ""}${p.team ? ` · ${p.team}` : " · FA"}`,
      sub: p.fa && p.fa.verdict ? `FA verdict: ${String(p.fa.verdict).toUpperCase()}` : "",
      // eephus-hub.js draws this into a 132x132 square with drawImage, which
      // has no object-fit - it MUST already be a square crop. 132 -> w_264,h_264.
      headshotURL: headshotURL(p.mlbam, 132),
      url: `eephus.io/projections/#player=${p.key}`,
      filename: `eephus-${p.key}-mlb-card.png`,
      caption: "eephus projection engine (proj_lgbm_v1) · bands = P10-P90 · Statcast percentiles vs Savant leaderboards",
    });
  }

  // Board payload loader, split out of boot() so the error-state Retry button
  // can re-fetch without stacking a second hashchange listener.
  function loadData() {
    const root = document.getElementById("proj-rows");
    if (!root) return;
    root.innerHTML = pxState("loading", "Loading projections.");
    // photo_ctx.json rides its OWN chain, not a Promise.all with the board:
    // (a) its failure is non-fatal and must never reach the board's catch, and
    // (b) the projections smoke test drives this file in py_mini_racer with
    // synchronous fake thenables that cannot satisfy Promise.all, so gating the
    // board render on a joined promise leaves the page stuck on "Loading" under
    // test. If the 117KB map lands first (it usually does against the 886KB
    // board), the first paint has photos; if it lands late, fillRowPhotos
    // re-fills the already-rendered wells. Fetched once per session.
    if (!PHOTO_CTX) {
      fetch("/data/photo_ctx.json", { cache: "force-cache" })
        .then(r => (r.ok ? r.json() : null))
        .then(d => { PHOTO_CTX = (d && d.ctx) || {}; if (DATA) fillRowPhotos(); })
        .catch(() => { PHOTO_CTX = {}; });
    }
    fetch("/data/mlb_projections.json", { cache: "no-cache" })
      .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
      .then(d => {
        DATA = d;
        // A card painted on its shard's frame stays put; the board only
        // backs the views the reader has not opened yet.
        if (state.player && PAINTED_PLAYER === state.player) return;
        render();
      })
      .catch(() => {
        if (state.player && PAINTED_PLAYER === state.player) return;
        root.innerHTML = pxState("failed", `Projections did not load. The nightly build may be writing it. <button class="chip" id="proj-retry" type="button">Retry</button>`);
        const retry = document.getElementById("proj-retry");
        if (retry) retry.onclick = loadData;
      });
  }

  function boot() {
    syncFromURL();
    if (!document.getElementById("proj-rows")) return;
    loadData();
    // A #player= link fetches its card beside the board, not after it.
    if (state.player) loadCard(state.player);
    window.addEventListener("hashchange", () => { syncFromURL(); render(); });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
