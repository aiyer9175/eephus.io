// Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
// Unauthorized copying of this file, via any medium is strictly prohibited
// Proprietary and confidential
// Written by Noah J. Dengler (@ARKNDJL), 2026
//
// The Dynasty sub-module of /fantasy/: the eFV-derived prospect board, Call-up
// Watch, and a keeper-value calculator. It was the whole of /dynasty/ between
// 2026-08-05 and 2026-08-07 and that dir is a redirect stub now.
//
// ONE EXPORTER, THREE CLIENTS. data/fantasy.json is still built by
// fantasy_export.py on one corpus (the expensive, memory-budgeted part). This
// file reads the two prospect sections out of it; assets/redraft.js reads the
// rest-of-season sections; assets/dfs.js reads its own daily slate payload.
// Nothing here recomputes a projection.
//
// ONE eFV BASIS. Every grade on this page is the served `efv` field, which
// fantasy_export produced through efv_board_scale.board_value (the site-wide
// board grade). This file does no grade arithmetic of any kind: no scale, no
// quantile, no blend. If a number here disagrees with PROSPX, the exporter is
// wrong, not the client, and that is the point of keeping it that way.
(function () {
  "use strict";
  var DATA_URL = "/data/fantasy.json";
  // THE FANTASY RANK (owner answer M21-4, 2026-09-25): MLB players and
  // prospects on one dynasty rank of projected FANTASY value, in the reader's
  // format, built by fantasy_rank.py beside the corpus. Its own sidecar,
  // fetched only when the Fantasy Rank tab or the keeper's All players pool
  // is opened, so a reader of the prospect board never downloads it.
  var RANK_URL = "/data/fantasy_rank.json";
  var S = { data: null, section: "dynasty", lens: "board", keeper: null, player: null,
            q: "", org: null, eta: null, tier: null,
            fmt: "fgp", pool: "prospects", kind: null,
            rank: null, rankLoading: false, rankErr: null };
  var SORT = { dynasty: { key: "rank", asc: true }, fantasy_rank: { key: "rank", asc: true } };
  var SORT_DEFAULTS = { dynasty: { key: "rank", asc: true } };
  var FMT_IDS = ["fgp", "sabr", "5x5", "4x4"];
  var POINTS_FMT = { fgp: 1, sabr: 1 };
  var LINKS = null;
  var LS_KEY = "eephus.dynasty.keeper";

  // ---- shell binding --------------------------------------------------------
  // Ids are read through a candidate list ending at the pre-split shared id, so
  // this file still mounts on an older shell and a missing element is never an
  // exception, only an unrendered surface. The combined /fantasy/ shell must
  // never expose that last candidate: all three clients end their list at it,
  // and one node shared by three clients is a triple-mount.
  function el(id) { return document.getElementById(id); }
  function pick() {
    for (var i = 0; i < arguments.length; i++) {
      var n = el(arguments[i]);
      if (n) return n;
    }
    return null;
  }
  function root() { return pick("dynasty-app-root", "fantasy-app-root"); }
  function bannerEl() { return pick("dynasty-banner", "fantasy-banner"); }
  // The shell reserves a bar above the section nav (the slot /redraft/ gives
  // its scoring selector). This module has no scoring formats, so the lens
  // control lives there instead of eating a line inside the board.
  function lensHost() { return pick("dynasty-scoring", "fantasy-scoring"); }
  function tabs() {
    var t = document.querySelectorAll(".mlbstats-sectionbtn[data-dynastysection]");
    if (t && t.length) return t;
    return document.querySelectorAll(".mlbstats-sectionbtn[data-fantasysection]");
  }
  function tabKey(b) {
    return b.getAttribute("data-dynastysection") || b.getAttribute("data-fantasysection");
  }

  // ---- host binding (the combined /fantasy/ page, 2026-08-07) ---------------
  // On /fantasy/ this file shares one document with assets/redraft.js and
  // assets/dfs.js, so assets/fantasy-hub.js owns the address bar and hands
  // this module only its own half of the hash. The corpus load goes through
  // the host too: data/fantasy.json is ~690KB (budgeted under 720KB by
  // test_fantasy_split) and Redraft reads the same file,
  // so a reader who opens both tabs downloads and parses it once.
  //
  // No host means the plain browser call, which keeps this file drivable
  // standalone in the JS-engine tests.
  var MODULE = "dynasty";
  function host() { return window.EEPHUS_FANTASY_HOST || null; }
  function hostHash() { var H = host(); return H ? H.hash(MODULE) : (location.hash || ""); }
  function hostWrite(h) {
    var H = host();
    if (H) { H.write(MODULE, h); return; }
    try { history.replaceState(null, "", h); } catch (e) { /* the hash is a nicety */ }
  }
  function hostLink(h) { var H = host(); return H ? H.link(MODULE, h) : h; }
  function hostRoute(fn) {
    var H = host();
    if (H) H.onChange(MODULE, fn);
    else window.addEventListener("hashchange", fn);
  }
  // Content stamp lookup for the standalone read. build_site emits
  // window.EEPHUS_DATA_VERS on pages whose payloads are build-time artifacts;
  // with a stamp the fetch rides a versioned URL under DEFAULT caching, and
  // without one (hand-served page, missing emission) the no-cache
  // revalidation below stays exactly as it was. The betting payloads never
  // enter the map: the close job mutates them intra-day with no rebuild.
  function stampedURL(url) {
    try {
      var vers = (typeof window !== "undefined" && window.EEPHUS_DATA_VERS) || null;
      var v = vers && vers[url.split("/").pop()];
      return v ? url + "?v=" + encodeURIComponent(v) : null;
    } catch (e) { return null; }
  }
  function load(url) {
    var H = host();
    if (H) return H.json(url);
    var stamped = stampedURL(url);
    var opts = stamped ? undefined : { cache: "no-cache" };
    if (stamped) url = stamped;
    return fetch(url, opts).then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    });
  }

  // ---- Diamond gate (wired, OFF) -------------------------------------------
  // The gate is read through window.EephusDiamond (assets/eephus-diamond.js),
  // the one authoritative contract, since 2026-08-16. The private copy that
  // lived here read EEPHUS_DIAMOND.isMember and .previewRows, keys the config
  // never defines, so flipping the flag would have capped PAYING members at 25
  // rows. Read defensively: the helper may be off the page (standalone test
  // drives), and its absence means the gate is open.
  function gate() { return window.EephusDiamond || null; }
  function gated() {
    var D = gate();
    try { return !!(D && D.gated()); } catch (e) { return false; }
  }
  function capRows(rows) {
    if (!gated()) return rows;
    return (rows || []).slice(0, gate().previewRows("dynasty"));
  }
  // The conversion line is a LINK. It was plain text on every Diamond page, so
  // the only route to the pricing page was the last item of a nav dropdown.
  function gateNote(total, shown) {
    if (!gated() || shown >= total) return "";
    return '<div class="dyn-note">Diamond preview: showing the top ' + shown + " of " +
      total + ' rows. <a class="dyn-name-link" href="/diamond/">Diamond funds the free site</a>.</div>';
  }

  // ---- helpers --------------------------------------------------------------
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
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
  function num(v, d) { return (v == null || isNaN(v)) ? "-" : Number(v).toFixed(d == null ? 1 : d); }
  function f0(v) { return num(v, 0); }
  // EVERY NAME OPENS THE IN-PAGE CARD. It is assembled from the payload this
  // browser already holds, so it resolves for every row rather than only the
  // ones player_links covers, and the card itself carries the outbound link to
  // the merged MLB page. The href is the FULL hash, so a card link copied out
  // of the page restores the board and lens it was opened from.
  function nameLink(mlbam, name) {
    return '<a class="dyn-name-link" href="' + esc(hashFor(mlbam)) + '">' + esc(name) + "</a>";
  }
  function teamLogo(team) {
    return (window.EEPHUS_HUB && EEPHUS_HUB.teamLogo && team) ? EEPHUS_HUB.teamLogo(team) : "";
  }
  function sections() { return (S.data && S.data.sections) || {}; }

  // ---- filter bar (2026-08-16) ----------------------------------------------
  // A VIEW over the served rows, never a re-rank: the diamond keeps the model
  // rank whatever survives the filter. Name is a case-insensitive substring;
  // org, ETA year and tier all validate against the SERVED board, so a stale
  // hash degrades to no filter rather than to an empty board. Duplicated per
  // client on purpose, the same trade the card machinery already made.
  function normQ(s) { return String(s == null ? "" : s).toLowerCase(); }
  function decodeQ(s) {
    try { return decodeURIComponent(s); } catch (e) { return ""; }
  }
  function filtersOn() { return !!(S.q || S.org || S.eta || S.tier); }
  // "Tier 1" -> "t1", "Elite" -> "elite": a hash-safe slug DERIVED from the
  // served label, so a new tier needs no change here.
  function tierSlug(t) {
    return normQ(t).replace("tier ", "t").replace(/[^a-z0-9]/g, "");
  }
  function passFilter(d) {
    if (!d) return false;
    if (S.q && normQ(d.name).indexOf(normQ(S.q)) < 0) return false;
    if (S.org && String(d.org || "").toUpperCase() !== S.org) return false;
    if (S.eta && String(d.eta || "") !== S.eta) return false;
    if (S.tier && tierSlug(d.tier) !== S.tier) return false;
    return true;
  }
  function filterRows(list) {
    return filtersOn() ? (list || []).filter(passFilter) : (list || []);
  }
  // full=false is the name-search-only bar (Keeper, Call-up Watch).
  function filterBar(list, full, shown) {
    var out = '<input type="search" id="dyn-f-q" class="dyn-f-q" placeholder="Filter by name"' +
      ' aria-label="Filter by prospect name" maxlength="40" value="' + esc(S.q) + '">';
    if (full) {
      var orgs = {}, etas = {}, tiers = {};
      (list || []).forEach(function (d) {
        if (d.org) orgs[d.org] = 1;
        if (d.eta != null) etas[String(d.eta)] = 1;
        if (d.tier) tiers[d.tier] = tiers[d.tier] || tierSlug(d.tier);
      });
      var orgList = Object.keys(orgs).sort();
      if (orgList.length > 1) {
        out += '<select id="dyn-f-org" data-team-picker aria-label="Filter by org"><option value="">All orgs</option>' +
          orgList.map(function (o) {
            return '<option value="' + esc(o) + '"' + (o === S.org ? " selected" : "") + ">" +
              esc(o) + "</option>";
          }).join("") + "</select>";
      }
      out += Object.keys(etas).sort().map(function (y) {
        var on = y === S.eta;
        return '<button type="button" class="dyn-f-chip' + (on ? " active" : "") +
          '" data-dynfeta="' + esc(y) + '" aria-pressed="' + (on ? "true" : "false") + '">' +
          esc(y) + "</button>";
      }).join("");
      var tierList = Object.keys(tiers);
      if (tierList.length > 1) {
        out += '<select id="dyn-f-tier" aria-label="Filter by tier"><option value="">All tiers</option>' +
          tierList.map(function (t) {
            return '<option value="' + esc(tiers[t]) + '"' + (tiers[t] === S.tier ? " selected" : "") +
              ">" + esc(t) + "</option>";
          }).join("") + "</select>";
      }
    }
    if (filtersOn()) {
      out += '<button type="button" class="dyn-f-chip" id="dyn-f-clear">Clear</button>';
      if (shown != null && list) {
        out += '<span class="dyn-f-count">' + shown + " of " + (list || []).length + " rows</span>";
      }
    }
    return '<div class="dyn-filterbar">' + out + "</div>";
  }
  function wireFilterBar(r) {
    var q = r.querySelector ? r.querySelector("#dyn-f-q") : null;
    if (q) q.addEventListener("input", function () {
      S.q = String(q.value || "").slice(0, 40);
      renderSection();
      writeHash();
      var again = r.querySelector("#dyn-f-q");
      if (again && again.focus) {
        again.focus();
        try { again.setSelectionRange(again.value.length, again.value.length); } catch (e) { /* fine */ }
      }
    });
    r.querySelectorAll("[data-dynfeta]").forEach(function (b) {
      b.addEventListener("click", function () {
        var v = b.getAttribute("data-dynfeta");
        S.eta = (S.eta === v) ? null : v;
        renderSection();
        writeHash();
      });
    });
    var o = r.querySelector ? r.querySelector("#dyn-f-org") : null;
    if (o) o.addEventListener("change", function () {
      S.org = o.value ? String(o.value).toUpperCase() : null;
      renderSection();
      writeHash();
    });
    var t = r.querySelector ? r.querySelector("#dyn-f-tier") : null;
    if (t) t.addEventListener("change", function () {
      S.tier = t.value || null;
      renderSection();
      writeHash();
    });
    var c = r.querySelector ? r.querySelector("#dyn-f-clear") : null;
    if (c) c.addEventListener("click", function () {
      S.q = ""; S.org = null; S.eta = null; S.tier = null;
      renderSection();
      writeHash();
    });
  }

  // ---- board columns --------------------------------------------------------
  // Ported verbatim from the retired /fantasy/ Dynasty board so the split moved
  // the page, not the numbers. get() only reads served fields; the formatters
  // only round. eFV rounds to NEAREST (it is not a scouting FV grade).
  var DYN_COLS = [
    { key: "rank", label: "#", where: "head", track: "38px", kind: "rank", asc: true,
      title: "Served dynasty rank. Sorting does not renumber it.",
      get: function (d) { return d.rank; } },
    { key: "name", label: "Prospect", where: "head", track: "minmax(0,1.7fr)", kind: "name", text: true, asc: true,
      title: "Sort by name", get: function (d) { return d.name; },
      cell: function (d) {
        return '<div class="dyn-id ff-id"><span class="mlb-name">' + teamLogo(d.org) + " " + nameLink(d.mlbam, d.name) +
          '</span><span class="mlb-sub">' + esc(d.pos || "") + (d.org ? " &middot; " + esc(d.org) : "") + "</span></div>";
      } },
    { key: "efv", label: "eFV", term: "xfv", where: "head", track: "72px", strong: true,
      title: "eFV board grade, same as PROSPX, rounded to nearest.",
      get: function (d) { return d.efv; }, fmt: f0 },
    { key: "eta", label: "ETA", where: "head", track: "72px", asc: true,
      title: "Estimated MLB arrival year",
      get: function (d) { return d.eta; }, cell: function (d) { return esc(d.eta || "-"); } },
    { key: "tier", label: "Tier", where: "head", track: "96px", asc: true,
      title: "Bucket of the served rank",
      get: function (d) { return d.rank; },
      cell: function (d) {
        var cls = d.tier === "Elite" ? " dyn-tier-elite" : (d.tier === "Tier 1" ? " dyn-tier-one" : "");
        return '<span class="dyn-tier' + cls + '">' + esc(d.tier) + "</span>";
      } },
    // The star BUCKET share (xfv p_bucket.star), not the published Star Odds
    // tier value the star_odds entry defines (audit QREC03), so it is named
    // and linked as the bucket.
    { key: "star", label: "Star bucket", term: "bust_prob", where: "tape",
      title: "Share of the star (Elite) outcome bucket",
      get: function (d) { return d.star; },
      cell: function (d) { return d.star == null ? "-" : num(d.star, 0) + "%"; } },
    { key: "bust", label: "Bust", term: "bust_prob", where: "tape", asc: true,
      title: "P(bust outcome)",
      get: function (d) { return d.bust; },
      cell: function (d) { return d.bust == null ? "-" : num(d.bust, 0) + "%"; } },
    { key: "surplus", label: "Surplus", term: "surplus_value", where: "tape",
      title: "Projected surplus, $M, from the served eFV export.",
      get: function (d) { return d.surplus; },
      cell: function (d) { return d.surplus == null ? "-" : "$" + num(d.surplus, 0) + "M"; } },
    { key: "keep", label: "Keep by", where: "tape",
      title: "Earliest keeper round whose pick number reaches his board rank in a prospects-only draft, " +
        "under your Keeper Calculator settings.",
      get: function (d) { return breakEvenRound(d.rank); },
      cell: function (d) {
        var r = breakEvenRound(d.rank);
        return r == null ? "-" : ("R" + r);
      } },
    { key: "band_hi", label: "Outlook", where: "tape",
      title: "P10-P90 career-value band, $M. Sorts on P90.",
      get: function (d) { return (d.band || [])[1]; },
      cell: function (d) {
        var b = d.band || [];
        return (b[0] != null && b[1] != null) ? ("$" + num(b[0], 0) + "-" + num(b[1], 0) + "M") : "-";
      } }
  ];

  // ---- card machinery -------------------------------------------------------
  // The shared .mlb-card system out of assets/site.css, same as the retired
  // /fantasy/ boards and the Projections / Free Agency boards.
  function colByKey(cols, k) {
    var out = null;
    (cols || []).forEach(function (c) { if (c.key === k) out = c; });
    return out;
  }
  function headCols(cols) { return cols.filter(function (c) { return c.where === "head"; }); }
  function tapeCols(cols) { return cols.filter(function (c) { return c.where === "tape"; }); }
  function labelOf(c) { return typeof c.label === "function" ? c.label() : c.label; }
  function glossLbl(c) {
    var l = esc(labelOf(c));
    return c.term ? '<span class="g-term" data-gl="' + esc(c.term) + '">' + l + "</span>" : l;
  }
  // Missing values sort LAST in both directions, so a blank never wins a board.
  function sortRowsBy(rows, cols, st) {
    var col = colByKey(cols, st.key);
    if (!col || !col.get) return rows.slice();
    var out = rows.slice();
    out.sort(function (a, b) {
      var va = col.get(a), vb = col.get(b);
      if (col.text) {
        var sa = va == null ? "" : String(va), sb = vb == null ? "" : String(vb);
        if (!sa && !sb) return 0;
        if (!sa) return 1;
        if (!sb) return -1;
        return st.asc ? sa.localeCompare(sb) : sb.localeCompare(sa);
      }
      var na = (va == null || isNaN(va)) ? null : Number(va);
      var nb = (vb == null || isNaN(vb)) ? null : Number(vb);
      if (na == null && nb == null) return 0;
      if (na == null) return 1;
      if (nb == null) return -1;
      return st.asc ? na - nb : nb - na;
    });
    return out;
  }
  // A div-bar toggle button, not a table head: no aria-sort (read only on a
  // columnheader or rowheader). The active chip carries .is-sorted (its paint in
  // assets/site.css), aria-pressed and visually hidden sort text (census M24-4).
  // The glossary hook rides the chip itself (audit QREA09): a .g-term span with
  // its own data-gl inside the chip was a second Tab stop nested in a button.
  // eephus-gl wire() gives the chip its aria-describedby and opens the
  // definition on hover and focus; the inner span keeps only the underline.
  function sortBtn(c, st) {
    var on = st.key === c.key;
    return '<span role="button" tabindex="0" data-dynsort="' + esc(c.key) + '"' +
      (on ? ' class="is-sorted"' : "") + ' aria-pressed="' + (on ? "true" : "false") + '"' +
      (c.term ? ' data-gl="' + esc(c.term) + '"' : "") +
      (c.title ? ' title="' + esc(c.title) + '"' : "") + ">" +
      (c.term ? '<span class="g-term">' + esc(labelOf(c)) + "</span>" : esc(labelOf(c))) +
      (on ? (st.asc ? " ▴" : " ▾") +
        '<span class="visually-hidden">, sorted ' + (st.asc ? "ascending" : "descending") + "</span>" : "") +
      "</span>";
  }
  function cellValue(c, row) {
    if (c.cell) return c.cell(row);
    var v = c.get ? c.get(row) : null;
    if (v == null) return "-";
    return c.fmt ? c.fmt(v) : esc(v);
  }
  // THE CARD CLASSES ARE THE SHARED ff- ONES, NOT dyn- COPIES. assets/site.css
  // carries the whole board-card block (fixed 104px height with a matching
  // contain-intrinsic-size, the rotated rank diamond, the hover shadow, the
  // phone-swipeable sort bar, the phone header collapse) under .ff-card /
  // .ff-rank / .ff-sortbar, written for exactly these four boards when they
  // lived at /fantasy/. The split renamed them to dyn-* and rd-*, which
  // silently dropped every one of those rules. Emitting the shared names is
  // the fix, and it is the fix rather than a local re-declaration because the
  // stylesheet already says so: one implementation, not two that drift.
  function cardCell(c, row, rk) {
    if (c.kind === "rank") return '<span class="ff-rank"><span class="ff-rank-i">' + esc(rk) + "</span></span>";
    if (c.kind === "name") return cellValue(c, row);
    return '<span class="mlb-metric' + (c.strong ? " ff-strong" : "") + '"><span class="mlb-metric-label">' +
      glossLbl(c) + "</span>" + cellValue(c, row) + "</span>";
  }
  function dynStripe(d) {
    if (d.tier === "Elite") return "var(--accent-gold)";
    if (d.tier === "Tier 1") return "var(--accent-cyan)";
    if (d.tier === "Tier 2") return "var(--accent-green)";
    return "var(--border)";
  }
  function renderCards(rows, cols, st, opts) {
    opts = opts || {};
    var hcols = headCols(cols), tcols = tapeCols(cols);
    var tracks = hcols.map(function (c) { return c.track; }).join(" ");
    var sorted = sortRowsBy(rows || [], cols, st);
    var total = sorted.length;
    sorted = capRows(sorted);
    var body = sorted.map(function (row, i) {
      var rk = opts.rankOf ? opts.rankOf(row, i) : (i + 1);
      var href = opts.hrefOf ? opts.hrefOf(row) : null;
      var chips = tcols.map(function (c) {
        return '<div class="mlb-chip"><b>' + esc(labelOf(c)) + "</b>" + cellValue(c, row) + "</div>";
      }).join("");
      return '<div class="mlb-card ff-card dyn-card" style="--org-color:' +
        (opts.stripeOf ? opts.stripeOf(row, rk) : "var(--border)") + ";grid-template-columns:" + tracks + '"' +
        (href ? ' tabindex="0" role="button" data-dynhref="' + esc(href) + '"' : "") + ">" +
        hcols.map(function (c) { return cardCell(c, row, rk); }).join("") +
        '<div class="mlb-tape"><div class="mlb-tape-inner">' + chips + "</div></div></div>";
    }).join("");
    if (!body) return pxState(opts.emptyKind || "empty", esc(opts.empty || "No rows to show yet."));
    var head = '<div class="mlb-card-head ff-card-head dyn-card-head" style="grid-template-columns:' + tracks + '">' +
      hcols.map(function (c) { return sortBtn(c, st); }).join("") + "</div>";
    var bar = tcols.length
      ? '<div class="ff-sortbar dyn-sortbar"><span class="ff-sortbar-lbl">Sort by</span>' +
        tcols.map(function (c) { return sortBtn(c, st); }).join("") + "</div>"
      : "";
    return bar + head + '<div class="mlb-card-list ff-card-list dyn-card-list">' + body + "</div>" +
      gateNote(total, sorted.length);
  }

  // ---- keeper settings ------------------------------------------------------
  // Everything the calculator needs about a league, in four numbers. Stored in
  // localStorage only. Nothing is sent anywhere: there is no server on this
  // page, and a keeper list is the reader's business.
  var KEEPER_DEFAULTS = { teams: 12, slot: 6, round: 5, window: 3 };
  function keeper() {
    if (S.keeper) return S.keeper;
    var k = null;
    try { k = JSON.parse(window.localStorage.getItem(LS_KEY) || "null"); } catch (e) { k = null; }
    S.keeper = {
      teams: intOr((k || {}).teams, KEEPER_DEFAULTS.teams, 2, 40),
      slot: intOr((k || {}).slot, KEEPER_DEFAULTS.slot, 1, 40),
      round: intOr((k || {}).round, KEEPER_DEFAULTS.round, 1, 60),
      window: intOr((k || {}).window, KEEPER_DEFAULTS.window, 1, 12)
    };
    if (S.keeper.slot > S.keeper.teams) S.keeper.slot = S.keeper.teams;
    return S.keeper;
  }
  function intOr(v, d, lo, hi) {
    var n = parseInt(v, 10);
    if (isNaN(n)) return d;
    return Math.max(lo, Math.min(hi, n));
  }
  function saveKeeper() {
    try { window.localStorage.setItem(LS_KEY, JSON.stringify(keeper())); } catch (e) { /* private mode */ }
  }
  // THE ONE PIECE OF ARITHMETIC ON THIS PAGE, and it is arithmetic, not a model.
  //
  //   the pick you spend keeping in round R  =  teams * (R - 1) + your slot
  //   the prospect is worth that pick when   =  that pick number >= his board rank
  //
  // so the break-even round is ceil((rank - slot) / teams) + 1, floored at 1.
  // We do NOT publish a dollar keeper value, because we have never fit one:
  // translating a dynasty rank into auction dollars needs league-specific
  // inflation data we do not have, and inventing the curve would be the exact
  // move this shop keeps a loss ledger to avoid.
  function breakEvenRound(rank) {
    if (rank == null || isNaN(rank)) return null;
    var k = keeper();
    var r = Math.ceil((Number(rank) - k.slot) / k.teams) + 1;
    return Math.max(1, r);
  }
  function costPick() {
    var k = keeper();
    return k.teams * (k.round - 1) + k.slot;
  }

  // ---- sections -------------------------------------------------------------
  var LENSES = [
    { id: "board", label: "Board order", sort: { key: "rank", asc: true },
      note: "Served rank." },
    { id: "contend", label: "Contending", sort: { key: "eta", asc: true },
      note: "Sorted by ETA, nearest first. Ranks unchanged." },
    { id: "rebuild", label: "Rebuilding", sort: { key: "star", asc: false },
      note: "Sorted by the star (Elite) bucket share, highest first. Ranks unchanged." }
  ];
  function lensById(id) {
    var out = LENSES[0];
    LENSES.forEach(function (l) { if (l.id === id) out = l; });
    return out;
  }
  function renderLensBar() {
    var l = lensById(S.lens);
    var btns = LENSES.map(function (x) {
      return '<button type="button" class="dyn-lensbtn' + (x.id === S.lens ? " active" : "") +
        '" data-dynlens="' + x.id + '">' + esc(x.label) + "</button>";
    }).join("");
    return '<div class="dyn-lensbar"><span class="dyn-lens-lbl">Lens</span>' + btns +
      '<span class="dyn-lens-note">' + esc(l.note) + "</span></div>";
  }
  function renderBoard() {
    var list = sections().dynasty || [];
    if (!list.length) {
      return '<div class="dyn-note">No dynasty rows yet; they fill on the nightly build. Nothing is broken.</div>';
    }
    // When the shell gives us the bar above the nav, the lens goes there and
    // the board keeps its full height. Otherwise it rides inline.
    var host = lensHost();
    var inlineLens = host ? "" : renderLensBar();
    // The blend disclosure stays: the rank is a stated convention over gated
    // upstream legs (fantasy_export._dynasty_prospects), never a fit.
    var intro = '<div class="dyn-note">Rank: ' + glossLbl({ label: "eFV", term: "xfv" }) + " first, then " +
      "the " + glossLbl({ label: "star (Elite) bucket share", term: "bust_prob" }) + " (up), bust share (down), " +
      "ETA proximity and surplus. A display ranking over served eFV numbers, not a separate model.</div>";
    var rows = filterRows(list);
    return intro + inlineLens + filterBar(list, true, rows.length) +
      renderCards(rows, DYN_COLS, SORT.dynasty, {
        rankOf: function (d) { return d.rank; },
        stripeOf: dynStripe,
        hrefOf: function (d) { return hashFor(d.mlbam); },
        empty: filtersOn() ? "No prospect matches the current filter."
          : "No dynasty rows yet; they fill on the nightly build.",
        emptyKind: filtersOn() ? "empty" : "unmeasured"
      });
  }
  function renderCallups() {
    var list = sections().callup_watch || [];
    if (!list.length) {
      return '<div class="dyn-note">No Call-up Watch rows in this build.</div>';
    }
    if (S.q) {
      list = list.filter(function (c) { return normQ(c.name).indexOf(normQ(S.q)) >= 0; });
      if (!list.length) {
        return filterBar(null, false) +
          '<div class="dyn-note">No call-up candidate matches the name filter.</div>';
      }
    }
    var shown = capRows(list);
    var rows = shown.map(function (c) {
      // eFV (round to nearest) leads. The consensus FV fallback displays as a
      // ceiling, which is the site-wide grade convention: scouting grades round
      // up, eFV and plus-stats round to nearest.
      var grade = (c.fvE != null) ? String(Math.round(c.fvE))
        : (c.fv != null ? String(Math.ceil(c.fv)) : "-");
      return '<tr><td class="dyn-nm">' + nameLink(c.mlbam, c.name) + "</td><td>" + esc(c.org) +
        "</td><td>" + esc(c.pos) + "</td><td>" + esc(c.eta) + '</td><td class="dyn-sc">' + grade + "</td></tr>";
    }).join("");
    return filterBar(null, false) +
      '<div class="dyn-note">ETA this season or next, ordered by eFV. Consensus FV (rounded up) where eFV is missing.</div>' +
      '<div class="mlbstats-scroll dyn-tablewrap"><table class="dyn-table mlbstats-table">' +
      '<thead><tr><th class="dyn-nm">Prospect</th><th>Org</th><th>Pos</th>' +
      "<th>" + glossLbl({ label: "ETA", term: "eta" }) + "</th>" +
      "<th>" + glossLbl({ label: "eFV", term: "xfv" }) + "</th></tr></thead><tbody>" +
      rows + "</tbody></table></div>" + gateNote(list.length, shown.length);
  }

  // ---- the Fantasy Rank ------------------------------------------------------
  // Every number here is served by fantasy_rank.py; this file sorts, filters
  // and rounds, nothing else. The rank is a pure function of the served value
  // in the chosen format, so no other board's order reaches it.
  function rankRows() { return (S.rank && S.rank.rows) || []; }
  // The load is synchronous under the test harness's promise stub, so the
  // re-render runs only when the answer lands AFTER the caller has painted.
  function loadRank() {
    if (S.rank || S.rankLoading) return;
    S.rankLoading = true;
    S.rankErr = null;
    var sync = true;
    load(RANK_URL).then(function (d) {
      S.rank = (d && d.rows) ? d : { rows: [] };
      S.rankLoading = false;
      if (!sync) renderSection();
    }).catch(function (e) {
      S.rankLoading = false;
      S.rankErr = String((e && e.message) || e);
      if (!sync) renderSection();
    });
    sync = false;
  }
  function fmtLabel(id) {
    var cat = (S.rank && S.rank.formats) || (S.data && S.data.scoring_catalog) || [];
    for (var i = 0; i < cat.length; i++) if (cat[i].id === id) return cat[i].label;
    return id;
  }
  function fmtVal(v) {
    if (v == null || isNaN(v)) return "-";
    return POINTS_FMT[S.fmt] ? Number(v).toFixed(0) : Number(v).toFixed(1);
  }
  function rankedRows() {
    var f = S.fmt;
    return rankRows().filter(function (d) { return d.rk && d.rk[f] != null; })
      .sort(function (a, b) { return a.rk[f] - b.rk[f]; });
  }
  function renderFmtBar() {
    var btns = FMT_IDS.map(function (id) {
      var on = id === S.fmt;
      return '<button type="button" class="dyn-lensbtn' + (on ? " active" : "") + '" data-dynfmt="' +
        id + '" aria-pressed="' + (on ? "true" : "false") + '">' + esc(fmtLabel(id)) + "</button>";
    }).join("");
    return '<div class="dyn-lensbar"><span class="dyn-lens-lbl">Format</span>' + btns +
      '<span class="dyn-lens-note">The Fantasy Rank re-ranks in the format you pick.</span></div>';
  }
  function frCols() {
    var seasons = (S.rank && S.rank.seasons) || [];
    var cols = [
      { key: "rank", label: "#", where: "head", track: "38px", kind: "rank", asc: true,
        title: "Fantasy Rank in the chosen format. Sorting does not renumber it.",
        get: function (d) { return d.rk ? d.rk[S.fmt] : null; } },
      { key: "name", label: "Player", where: "head", track: "minmax(0,1.7fr)", kind: "name", text: true, asc: true,
        title: "Sort by name", get: function (d) { return d.name; },
        cell: function (d) {
          return '<div class="dyn-id ff-id"><span class="mlb-name">' + teamLogo(d.team) + " " +
            nameLink(d.mlbam, d.name) + '</span><span class="mlb-sub">' + esc(d.pos || "") +
            (d.team ? " &middot; " + esc(d.team) : "") + "</span></div>";
        } },
      { key: "value", label: "Value", where: "head", track: "84px", strong: true,
        title: "Discounted value above replacement over the horizon, in the chosen format.",
        get: function (d) { return d.v ? d.v[S.fmt] : null; }, fmt: fmtVal },
      { key: "kind", label: "Type", where: "head", track: "84px", text: true, asc: true,
        title: "MLB player or prospect",
        get: function (d) { return d.kind === "prospect" ? "Prospect" : "MLB"; } },
      { key: "eta", label: "ETA", where: "head", track: "64px", asc: true,
        title: "Prospect ETA year; MLB players show a dash.",
        get: function (d) { return d.kind === "prospect" ? d.eta : null; },
        cell: function (d) { return esc(d.kind === "prospect" ? (d.eta || "-") : "-"); } }
    ];
    seasons.forEach(function (yr, t) {
      cols.push({ key: "s" + t, label: String(yr), where: "tape",
        title: "Value above replacement in " + yr + (t ? ", before the discount" : "") +
          ", weighted by the chance he has arrived (prospects).",
        get: function (d) { return d.s && d.s[S.fmt] ? d.s[S.fmt][t] : null; }, fmt: fmtVal });
    });
    cols.push({ key: "arrive", label: "Arrived by " + (seasons[seasons.length - 1] || ""), where: "tape",
      title: "P(arrived) by the last horizon season, from the ETA model's arrival curve for his level.",
      get: function (d) { return (d.p && d.p.length) ? d.p[d.p.length - 1] : null; },
      cell: function (d) {
        return (d.p && d.p.length) ? num(d.p[d.p.length - 1] * 100, 0) + "%" : "MLB";
      } });
    cols.push({ key: "board", label: "Board #", where: "tape", asc: true,
      title: "His Dynasty Board rank (prospects only).",
      get: function (d) { return d.board_rank; } });
    return cols;
  }
  function frStripe(d) {
    return d.kind === "prospect" ? "var(--accent-cyan)" : "var(--border)";
  }
  function kindChips() {
    var opts = [["", "All players"], ["mlb", "MLB"], ["prospect", "Prospects"]];
    return opts.map(function (o) {
      var on = (S.kind || "") === o[0];
      return '<button type="button" class="dyn-f-chip' + (on ? " active" : "") + '" data-dynkind="' +
        o[0] + '" aria-pressed="' + (on ? "true" : "false") + '">' + esc(o[1]) + "</button>";
    }).join("");
  }
  // The backtest sentence is assembled from the served artifact numbers, so
  // it can only say what the registered backtest artifact measured.
  function backtestNote(bt) {
    if (!bt || bt.rho_prospect_leg == null || bt.rho_consensus_fv == null) {
      return "The prospect leg has no backtest reading in this build.";
    }
    var lead = bt.rho_prospect_leg >= bt.rho_consensus_fv ? "above" : "below";
    var ci = (bt.lo95 != null && bt.hi95 != null)
      ? " (difference " + num(bt.rho_prospect_leg - bt.rho_consensus_fv, 2) + ", 95% interval " +
        num(bt.lo95, 2) + " to " + num(bt.hi95, 2) + ")" : "";
    return "Prospect leg check: on the " + esc((bt.vintages || []).join(" and ")) + " prospect classes, " +
      "this leg's order matched the fantasy value those players went on to produce at Spearman " +
      num(bt.rho_prospect_leg, 2) + ", " + lead + " the consensus FV order at " +
      num(bt.rho_consensus_fv, 2) + ci + ". Read the prospect order with that in mind.";
  }
  function renderRankBoard() {
    if (!S.rank) {
      loadRank();
      if (!S.rank) {
        return S.rankErr
          ? pxState("failed", "<strong>The Fantasy Rank failed to load.</strong> " + esc(S.rankErr), "dyn-error")
          : pxState("loading", "Loading the Fantasy Rank.");
      }
    }
    var all = rankedRows();
    if (!rankRows().length) {
      return '<div class="dyn-note">No Fantasy Rank rows in this build; they fill on the monthly build. ' +
        "Nothing is broken.</div>";
    }
    var R = S.rank;
    var intro = '<div class="dyn-note">' + (R.basis || []).map(esc).join(" ") +
      " A /fantasy/ rank on projected fantasy value only: it reads no WAR and does not reorder " +
      "/projections/. " + esc(fmtLabel(S.fmt)) + ": " +
      ((R.n_ranked && R.n_ranked[S.fmt] != null) ? R.n_ranked[S.fmt] : all.length) +
      " players clear replacement over the horizon; listed are the top " + esc(R.serve_top_n || 400) +
      " in any format and every Dynasty Board prospect.</div>" +
      '<div class="dyn-note">' + backtestNote(R.backtest) + "</div>";
    var rows = all.filter(function (d) {
      if (S.kind && d.kind !== S.kind) return false;
      if (S.q && normQ(d.name).indexOf(normQ(S.q)) < 0) return false;
      return true;
    });
    var unranked = rankRows().filter(function (d) {
      return d.kind === "prospect" && (!d.rk || d.rk[S.fmt] == null);
    }).length;
    var tail = unranked ? '<div class="dyn-note">' + unranked + " board prospects sit at or below " +
      "replacement in every season of the horizon in this format and are not ranked.</div>" : "";
    var bar = '<div class="dyn-filterbar"><input type="search" id="dyn-f-q" class="dyn-f-q" ' +
      'placeholder="Filter by name" aria-label="Filter by player name" maxlength="40" value="' +
      esc(S.q) + '">' + kindChips() +
      ((S.q || S.kind) ? '<span class="dyn-f-count">' + rows.length + " of " + all.length + " rows</span>" : "") +
      "</div>";
    return intro + bar + renderCards(rows, frCols(), SORT.fantasy_rank, {
      rankOf: function (d) { return d.rk[S.fmt]; },
      stripeOf: frStripe,
      hrefOf: function (d) { return hashFor(d.mlbam); },
      empty: "No player matches the current filter."
    }) + tail;
  }

  // ---- keeper calculator ----------------------------------------------------
  function keeperVerdict(d) {
    var pick = costPick(), be = breakEvenRound(d.rank);
    var edge = pick - d.rank;
    return { pick: pick, be: be, edge: edge, keep: edge >= 0 };
  }
  // THE POOL TOGGLE (owner answer M21-3, 2026-09-25). "Prospects only" is the
  // default and is the calculator exactly as it was: the pick against the
  // prospect board rank, a farm-draft verdict. "All players" compares the
  // same pick with the Fantasy Rank, a draft that holds MLB players and
  // prospects, in the chosen format. The page names the pool either way.
  function poolBar() {
    var opts = [["prospects", "Prospects only"], ["all", "All players"]];
    return '<div class="dyn-lensbar" role="group" aria-label="Keeper verdict pool">' +
      '<span class="dyn-lens-lbl">Pool</span>' + opts.map(function (o) {
        var on = S.pool === o[0];
        return '<button type="button" class="dyn-lensbtn' + (on ? " active" : "") + '" data-dynpool="' +
          o[0] + '" aria-pressed="' + (on ? "true" : "false") + '">' + esc(o[1]) + "</button>";
      }).join("") + '<span class="dyn-lens-note">' +
      (S.pool === "all"
        ? "This verdict answers a draft of MLB players and prospects, ranked on the Fantasy Rank in " +
          esc(fmtLabel(S.fmt)) + "."
        : "This verdict answers a prospects-only draft, ranked on the Dynasty Board.") +
      "</span></div>";
  }
  function renderKeeperAll(k, form) {
    var explain =
      '<div class="dyn-note">Pick spent against Fantasy Rank in a draft that holds MLB players and ' +
      "prospects, in " + esc(fmtLabel(S.fmt)) + ". No dynasty dollar curve is fit, so no dollar value is " +
      "shown. With " + k.teams + " teams and pick " + k.slot + ", a round " + k.round +
      " keeper costs pick <b>" + costPick() + "</b> of that draft. Settings stay in this browser.</div>";
    if (!S.rank) {
      loadRank();
      if (!S.rank) {
        return poolBar() + explain + form + (S.rankErr
          ? pxState("failed", "<strong>The Fantasy Rank failed to load.</strong> " + esc(S.rankErr), "dyn-error")
          : pxState("loading", "Loading the Fantasy Rank."));
      }
    }
    var list = rankedRows().map(function (d) {
      return { mlbam: d.mlbam, name: d.name, org: d.team, pos: d.pos, kind: d.kind,
               eta: d.eta, rank: d.rk[S.fmt], value: d.v ? d.v[S.fmt] : null };
    });
    if (!list.length) {
      return poolBar() + explain + form + '<div class="dyn-note">No Fantasy Rank rows in this build. ' +
        "The pick math above still updates.</div>";
    }
    if (S.q) {
      list = list.filter(function (d) { return normQ(d.name).indexOf(normQ(S.q)) >= 0; });
      if (!list.length) {
        return poolBar() + explain + form + filterBar(null, false) +
          '<div class="dyn-note">No player matches the name filter.</div>';
      }
    }
    var shown = capRows(list.slice(0, 150));
    var rows = shown.map(function (d) {
      var v = keeperVerdict(d);
      return "<tr>" +
        '<td class="mlbstats-col-rank">' + esc(d.rank) + "</td>" +
        '<td class="dyn-nm">' + teamLogo(d.org) + " " + nameLink(d.mlbam, d.name) + "</td>" +
        "<td>" + esc(d.pos || "") + "</td>" +
        "<td>" + (d.kind === "prospect" ? "Prospect" : "MLB") + "</td>" +
        "<td>" + fmtVal(d.value) + "</td>" +
        "<td>R" + esc(v.be) + "</td>" +
        '<td class="dyn-sc ' + (v.keep ? "dyn-pos" : "dyn-neg") + '">' +
        (v.keep ? "keep" : "let go") + " (" + (v.edge >= 0 ? "+" : "") + esc(v.edge) + ")</td>" +
        "</tr>";
    }).join("");
    return poolBar() + explain + form + filterBar(null, false) +
      '<div class="dyn-note">Edge = pick spent minus Fantasy Rank; positive means keep in a draft of ' +
      "MLB players and prospects. Keep by: earliest round where edge is 0 or more.</div>" +
      '<div class="mlbstats-scroll dyn-tablewrap"><table class="dyn-table mlbstats-table">' +
      '<thead><tr><th class="mlbstats-col-rank">#</th><th class="dyn-nm">Player</th><th>Pos</th>' +
      "<th>Type</th><th>Value</th>" +
      "<th>Keep by</th><th>Verdict at R" + esc(k.round) + "</th></tr></thead><tbody>" + rows + "</tbody></table></div>" +
      gateNote(list.length, shown.length);
  }
  function renderKeeper() {
    var k = keeper();
    var list = sections().dynasty || [];
    var season = (S.data && S.data.season) || null;
    var form =
      '<div class="dyn-form">' +
      field("dyn-k-teams", "Teams in your league", k.teams, 2, 40) +
      field("dyn-k-slot", "Your first-round pick slot", k.slot, 1, k.teams) +
      field("dyn-k-round", "Round the keeper costs you", k.round, 1, 60) +
      field("dyn-k-window", "Your contention window, in years", k.window, 1, 12) +
      '<button type="button" class="dyn-btn" id="dyn-k-reset">Reset</button>' +
      "</div>";
    if (S.pool === "all") return renderKeeperAll(k, form);
    // THE BASIS (2026-09-25). The board ranks prospects only, so the verdict is
    // a prospects-only (farm or minors) draft verdict. It used to say "costs
    // pick 54 overall", which read as the main draft, where a prospect goes far
    // later than his prospect rank; no combined MLB-plus-prospect rank is served
    // here, so the page states the basis instead of implying the other one.
    var explain = poolBar() +
      '<div class="dyn-note">Pick spent against board rank in a prospects-only draft (a farm or minors ' +
      "draft). The board ranks prospects only, so in a draft that also holds MLB players a prospect goes " +
      "later than his board rank; the All players pool above answers that draft on the Fantasy Rank. " +
      "No dynasty dollar curve is fit, so no " +
      "dollar value is shown. With " + k.teams + " teams and pick " + k.slot + ", a round " + k.round +
      " keeper costs pick <b>" + costPick() + "</b> of that draft. The window only marks whether the ETA " +
      "lands inside it; the verdict does not read it. Settings stay in this browser.</div>";
    if (!list.length) {
      return explain + form + '<div class="dyn-note">No board rows yet. The pick math above still updates.</div>';
    }
    // Name search narrows BEFORE the 150-row cap, so a keeper deep on the
    // board is findable rather than cut off by the cap.
    if (S.q) {
      list = list.filter(function (d) { return normQ(d.name).indexOf(normQ(S.q)) >= 0; });
      if (!list.length) {
        return explain + form + filterBar(null, false) +
          '<div class="dyn-note">No prospect matches the name filter.</div>';
      }
    }
    var shown = capRows(list.slice(0, 150));
    var rows = shown.map(function (d) {
      var v = keeperVerdict(d);
      var inWindow = (d.eta && season) ? ((Number(d.eta) - Number(season)) <= k.window) : null;
      return "<tr>" +
        // .mlbstats-col-rank rather than .dyn-rk: site.css UNDOES the frozen
        // first column on any .dyn-table whose first cell is .dyn-rk, because
        // freezing a rank digit pins the number and scrolls the name away. The
        // shared class on the header AND the cell is the module-side fix that
        // rule asks for, and it pins the rank narrow with the NAME beside it.
        '<td class="mlbstats-col-rank">' + esc(d.rank) + "</td>" +
        '<td class="dyn-nm">' + teamLogo(d.org) + " " + nameLink(d.mlbam, d.name) + "</td>" +
        "<td>" + esc(d.pos || "") + "</td>" +
        "<td>" + f0(d.efv) + "</td>" +
        "<td>" + esc(d.eta || "-") +
        (inWindow == null ? "" : ' <span class="dyn-win ' + (inWindow ? "dyn-win-in" : "dyn-win-out") +
          '">' + (inWindow ? "in window" : "after window") + "</span>") + "</td>" +
        "<td>R" + esc(v.be) + "</td>" +
        '<td class="dyn-sc ' + (v.keep ? "dyn-pos" : "dyn-neg") + '">' +
        (v.keep ? "keep" : "let go") + " (" + (v.edge >= 0 ? "+" : "") + esc(v.edge) + ")</td>" +
        "</tr>";
    }).join("");
    return explain + form + filterBar(null, false) +
      '<div class="dyn-note">Edge = pick spent minus board rank; positive means keep in a prospects-only ' +
      "draft. Keep by: earliest round where edge is 0 or more.</div>" +
      '<div class="mlbstats-scroll dyn-tablewrap"><table class="dyn-table mlbstats-table">' +
      '<thead><tr><th class="mlbstats-col-rank">#</th><th class="dyn-nm">Prospect</th><th>Pos</th>' +
      "<th>" + glossLbl({ label: "eFV", term: "xfv" }) + "</th>" +
      "<th>" + glossLbl({ label: "ETA", term: "eta" }) + "</th>" +
      "<th>Keep by</th><th>Verdict at R" + esc(k.round) + "</th></tr></thead><tbody>" + rows + "</tbody></table></div>" +
      gateNote(list.length, shown.length);
  }
  function field(id, label, val, lo, hi) {
    return '<label class="dyn-field"><span>' + esc(label) + '</span><input type="number" id="' + id +
      '" value="' + esc(val) + '" min="' + lo + '" max="' + hi + '" inputmode="numeric"></label>';
  }

  // ---- share card -----------------------------------------------------------
  function shareSpec() {
    // The graphic follows the board ON SCREEN, filter included (2026-08-16).
    var list = sortRowsBy(filterRows(sections().dynasty || []), DYN_COLS, SORT.dynasty);
    return {
      kind: "board", module: "Dynasty", accentToken: "--accent-cyan",
      title: "Dynasty Prospect Board",
      subtitle: (S.data && S.data.season ? "Season " + S.data.season + " · " : "") +
        list.length + " prospects · " + lensById(S.lens).label,
      url: "eephus.io/dynasty", filenameBase: "eephus-dynasty-board",
      caption: "eFV board grades. Display ranking over served numbers.",
      board: {
        columns: [{ label: "#", frac: 0.07, align: "right" }, { label: "Prospect", frac: 0.4 },
                  { label: "eFV", frac: 0.13, align: "right" }, { label: "ETA", frac: 0.13, align: "right" },
                  { label: "Star bucket", frac: 0.13, align: "right" }, { label: "Surplus", frac: 0.14, align: "right" }],
        rows: list.map(function (d) {
          return { cells: [{ t: d.rank }, { t: d.name || "-", sub: d.org || undefined },
                           { t: f0(d.efv), c: "accent" }, { t: d.eta || "-" },
                           { t: d.star == null ? "-" : num(d.star, 0) + "%" },
                           { t: d.surplus == null ? "-" : "$" + num(d.surplus, 0) + "M" }] };
        }),
        counts: [10, 25, 50]
      }
    };
  }

  // ---- render + wiring ------------------------------------------------------
  function isBoard() { return S.section === "dynasty"; }
  // The Fantasy Rank tab, and the keeper on its All players pool, read the
  // rank sidecar and take the format control.
  function usesRank() { return S.section === "fantasy_rank" || (S.section === "keeper" && S.pool === "all"); }
  function activeCols() { return S.section === "fantasy_rank" ? frCols() : DYN_COLS; }
  function activeSort() { return S.section === "fantasy_rank" ? SORT.fantasy_rank : SORT.dynasty; }
  function renderSection() {
    var r = root();
    if (!r) return;
    var html;
    if (S.section === "callups") html = renderCallups();
    else if (S.section === "keeper") html = renderKeeper();
    else if (S.section === "fantasy_rank") html = renderRankBoard();
    else html = renderBoard();
    if (isBoard() && window.EEPHUS_GFX && EEPHUS_GFX.chipHTML) {
      html = '<div class="dyn-tools">' + EEPHUS_GFX.chipHTML("dyn-gfx", "Generate GFX") + "</div>" + html;
    }
    r.innerHTML = html;
    // The lens belongs to the board. On the other two tabs the bar is emptied
    // rather than left showing a control that no longer does anything.
    var host = lensHost();
    if (host) {
      host.innerHTML = (isBoard() && (sections().dynasty || []).length) ? renderLensBar()
        : (usesRank() ? renderFmtBar() : "");
      wireLens(host);
    }
    wireSection(r);
    if (window.EEPHUS_GL && EEPHUS_GL.wire) EEPHUS_GL.wire(r);
  }
  function wireLens(scope) {
    scope.querySelectorAll("[data-dynlens]").forEach(function (b) {
      b.addEventListener("click", function () {
        S.lens = b.getAttribute("data-dynlens");
        var l = lensById(S.lens);
        SORT.dynasty = { key: l.sort.key, asc: l.sort.asc };
        renderSection();
        writeHash();
      });
    });
    scope.querySelectorAll("[data-dynfmt]").forEach(function (b) {
      b.addEventListener("click", function () {
        var v = b.getAttribute("data-dynfmt");
        if (FMT_IDS.indexOf(v) < 0) return;
        S.fmt = v;
        renderSection();
        writeHash();
      });
    });
  }
  function wireSection(r) {
    wireLens(r);
    wireFilterBar(r);
    r.querySelectorAll("[data-dynpool]").forEach(function (b) {
      b.addEventListener("click", function () {
        S.pool = b.getAttribute("data-dynpool") === "all" ? "all" : "prospects";
        renderSection();
        writeHash();
      });
    });
    r.querySelectorAll("[data-dynkind]").forEach(function (b) {
      b.addEventListener("click", function () {
        var v = b.getAttribute("data-dynkind");
        S.kind = (v === "mlb" || v === "prospect") ? v : null;
        renderSection();
        writeHash();
      });
    });
    r.querySelectorAll("[data-dynsort]").forEach(function (h) {
      function fire(refocus) {
        var st = activeSort();
        var k = h.getAttribute("data-dynsort"), c = colByKey(activeCols(), k);
        if (st.key === k) st.asc = !st.asc;
        else { st.key = k; st.asc = !!(c && c.asc); }
        renderSection();
        writeHash();
        if (!refocus) return;
        var again = r.querySelector('[data-dynsort="' + k + '"]');
        if (again && again.focus) again.focus();
      }
      h.addEventListener("click", function () { fire(false); });
      h.addEventListener("keydown", function (e) {
        if (e.key !== "Enter" && e.key !== " ") return;
        e.preventDefault();
        fire(true);
      });
    });
    // Whole-card activation. The guard must EXCLUDE THE CARD ITSELF: the card
    // carries role="button" and closest() starts at the element it is called
    // on, so a naive closest("a,button,[role=button]") matches the card and
    // returns before the handler can open anything.
    r.querySelectorAll("[data-dynhref]").forEach(function (c) {
      function onCard(e) {
        var t = e.target.closest("a,button,[role=button]");
        return !t || t === c;
      }
      function open() { location.href = c.getAttribute("data-dynhref"); }
      c.addEventListener("click", function (e) { if (onCard(e)) open(); });
      c.addEventListener("keydown", function (e) {
        if (e.key !== "Enter" && e.key !== " ") return;
        if (!onCard(e)) return;
        e.preventDefault();
        open();
      });
    });
    var gfx = r.querySelector("#dyn-gfx");
    if (gfx) gfx.addEventListener("click", function () {
      if (window.EEPHUS_GFX) EEPHUS_GFX.open(shareSpec());
    });
    bindKeeperInputs(r);
  }
  function bindKeeperInputs(r) {
    var map = { "dyn-k-teams": "teams", "dyn-k-slot": "slot",
                "dyn-k-round": "round", "dyn-k-window": "window" };
    Object.keys(map).forEach(function (id) {
      var n = r.querySelector("#" + id);
      if (!n) return;
      n.addEventListener("change", function () {
        var k = keeper();
        var lim = { teams: [2, 40], slot: [1, Math.max(2, k.teams)], round: [1, 60], window: [1, 12] }[map[id]];
        k[map[id]] = intOr(n.value, KEEPER_DEFAULTS[map[id]], lim[0], lim[1]);
        if (k.slot > k.teams) k.slot = k.teams;
        saveKeeper();
        renderSection();
        var again = root() && root().querySelector("#" + id);
        if (again && again.focus) again.focus();
      });
    });
    var rst = r.querySelector("#dyn-k-reset");
    if (rst) rst.addEventListener("click", function () {
      S.keeper = { teams: KEEPER_DEFAULTS.teams, slot: KEEPER_DEFAULTS.slot,
                   round: KEEPER_DEFAULTS.round, window: KEEPER_DEFAULTS.window };
      saveKeeper();
      renderSection();
    });
  }
  function syncTabs() {
    tabs().forEach(function (b) {
      var on = tabKey(b) === S.section;
      b.classList.toggle("active", on);
      b.setAttribute("aria-selected", on ? "true" : "false");
    });
  }
  function wireTabs() {
    tabs().forEach(function (b) {
      b.addEventListener("click", function () {
        S.section = tabKey(b);
        syncTabs();
        renderSection();
        writeHash();
      });
    });
  }

  // ---- hash router ----------------------------------------------------------
  //   #section=dynasty|callups|keeper   ("board" is accepted as an alias)
  //   #lens=board|contend|rebuild
  //   #sort=<column>.<a|d>
  //   #q= #team= #eta= #tier=   the filter bar (2026-08-16); team is the org
  //                             code, and org / eta / tier all validate against
  //                             the SERVED board rows
  //   #player=<mlbam>   the fantasy player card, over whatever board is under it
  // Every key is optional and validated; a stale or hand-edited URL degrades to
  // the default rather than to a broken board.
  //
  // The canonical section name is the one the SHELL's nav attribute carries
  // ("dynasty"), because syncTabs compares the two directly and a mismatch
  // renders the right board under a nav that announces the wrong tab.
  //   #section=fantasy_rank   the Fantasy Rank (2026-10-01)
  //   #fmt=fgp|sabr|5x5|4x4   its format (fgp, the default, is left out)
  //   #kind=mlb|prospect      its type filter
  //   #pool=all               the keeper's All players pool (prospects only is the default)
  var SECTIONS = ["dynasty", "board", "callups", "keeper", "fantasy_rank"];
  var SECTION_ALIAS = { board: "dynasty" };
  var LAST_HASH = null;
  function hashParam(h, key, pat) {
    var m = new RegExp("(?:^#|[#&])" + key + "=(" + pat + ")(?:&|$)").exec(h || "");
    return m ? m[1] : null;
  }
  // EVERY CALLER REWRITES THE ADDRESS BAR AFTERWARDS, so an invalid section, an
  // ALIASED one ("#section=board" resolves to dynasty and the URL should say
  // dynasty), and a hash carrying a card all normalize the same way. This used
  // to return a "was it canonical" flag and the callers rewrote on a false; the
  // flag could not name every case once the card joined the hash.
  function readHash() {
    var h = hostHash();
    var s = hashParam(h, "section", SECTIONS.join("|"));
    if (s) S.section = SECTION_ALIAS[s] || s;
    var l = hashParam(h, "lens", LENSES.map(function (x) { return x.id; }).join("|"));
    if (l) {
      S.lens = l;
      var lz = lensById(l);
      SORT.dynasty = { key: lz.sort.key, asc: lz.sort.asc };
    }
    var v = hashParam(h, "sort", "[A-Za-z0-9_]+\\.[ad]");
    if (v) {
      var i = v.lastIndexOf("."), k = v.slice(0, i), c = colByKey(DYN_COLS, k);
      if (c && c.get) {
        SORT.dynasty.key = k;
        SORT.dynasty.asc = (v.slice(i + 1) === "a");
      }
    }
    // The filter half, validated against the SERVED board rows so a stale hash
    // degrades to no filter. Read unconditionally: a hash WITHOUT the key
    // clears the filter, which is what makes the Back button undo one.
    var rows = sections().dynasty || [];
    var q = hashParam(h, "q", "[^&]+");
    S.q = q ? decodeQ(q).slice(0, 40) : "";
    var org = hashParam(h, "team", "[A-Za-z]{2,3}");
    S.org = (org && rows.some(function (d) {
      return String(d.org || "").toUpperCase() === org.toUpperCase();
    })) ? org.toUpperCase() : null;
    var eta = hashParam(h, "eta", "\\d{4}");
    S.eta = (eta && rows.some(function (d) { return String(d.eta || "") === eta; })) ? eta : null;
    var tier = hashParam(h, "tier", "[a-z0-9]{1,8}");
    S.tier = (tier && rows.some(function (d) { return tierSlug(d.tier) === tier; })) ? tier : null;
    var fmt = hashParam(h, "fmt", "fgp|sabr|5x5|4x4");
    S.fmt = fmt || "fgp";
    S.pool = hashParam(h, "pool", "all|prospects") === "all" ? "all" : "prospects";
    S.kind = hashParam(h, "kind", "mlb|prospect");
    S.player = hashParam(h, "player", "\\d+");
  }
  // The BOARD half of the hash, card left out: hashFor() builds a card link
  // over the current board, and onHashChange compares before against after so
  // opening a card does not re-render the board underneath it.
  function boardHash() {
    var parts = ["section=" + S.section];
    if (S.lens !== "board") parts.push("lens=" + S.lens);
    var st = SORT.dynasty, d = SORT_DEFAULTS.dynasty;
    if (st.key && !(st.key === d.key && !!st.asc === !!d.asc)) {
      parts.push("sort=" + st.key + "." + (st.asc ? "a" : "d"));
    }
    if (S.q) parts.push("q=" + encodeURIComponent(S.q));
    if (S.org) parts.push("team=" + S.org);
    if (S.eta) parts.push("eta=" + S.eta);
    if (S.tier) parts.push("tier=" + S.tier);
    if (S.fmt && S.fmt !== "fgp") parts.push("fmt=" + S.fmt);
    if (S.kind) parts.push("kind=" + S.kind);
    if (S.pool === "all") parts.push("pool=all");
    return "#" + parts.join("&");
  }
  // The module's OWN hash. hashFor() is the same string routed through the
  // host, because an href a reader copies has to carry the module prefix too.
  function localHash() {
    return S.player ? (boardHash() + "&player=" + S.player) : boardHash();
  }
  function hashFor(mlbam) { return hostLink(boardHash() + "&player=" + mlbam); }
  function writeHash() {
    LAST_HASH = localHash();
    hostWrite(LAST_HASH);
  }
  function onHashChange() {
    if (!S.data) return;
    if (hostHash() === LAST_HASH) return;
    var before = boardHash();
    readHash();
    if (boardHash() !== before) { syncTabs(); renderSection(); }
    syncCard();
    writeHash();
  }
  hostRoute(onHashChange);

  // ---- player card ----------------------------------------------------------
  // The card module owns the overlay; this file hands it the payload and the
  // one piece of arithmetic that belongs to this page, the keeper break-even
  // round. No score line: the league-format port lives in assets/redraft.js and
  // a second copy here would be a second implementation nobody is comparing.
  function card() { return window.EEPHUS_FANTASY_CARD || null; }
  // THE LINKS SIDECAR IS READ ON A CARD, NOT AT BOOT (audit QREP15).
  // player_links (about 1.9 MB) feeds only the card's outbound "Full MLB card"
  // link, so it is asked for the first time a card opens; until it lands the
  // card says nothing about that link rather than "No MLB card yet".
  var LINKS_ASKED = false, LINKS_DONE = false;
  function wantLinks() {
    if (LINKS || LINKS_ASKED || !S.player || !(window.EEPHUS_HUB && EEPHUS_HUB.links)) return;
    LINKS_ASKED = true;
    EEPHUS_HUB.links().then(function (L) { LINKS = L || null; LINKS_DONE = true; syncCard(); },
                            function () { LINKS_DONE = true; syncCard(); });
  }
  function syncCard() { var C = card(); if (C) { wantLinks(); C.sync(S.player); } }
  function attachCard() {
    var C = card();
    if (!C) return;
    C.attach({
      payload: function () { return S.data; },
      links: function () { return LINKS; },
      linksPending: function () { return LINKS_ASKED && !LINKS_DONE; },
      keeperRound: breakEvenRound,
      onClose: function () { S.player = null; writeHash(); }
    });
  }

  // ---- boot -----------------------------------------------------------------
  function errorState(msg) {
    var r = root();
    if (r) r.innerHTML = pxState("failed", "<strong>Data failed to load.</strong> " +
      esc(msg || "") + ' <button type="button" id="dyn-retry" class="dyn-btn">Retry</button>', "dyn-error");
    var rb = el("dyn-retry");
    if (rb) rb.addEventListener("click", boot);
  }
  function notReady() {
    var r = root();
    if (r) r.innerHTML = '<div class="dyn-note">The dynasty payload is not built yet (nightly build).</div>';
  }
  function onData(d) {
    if (!d || !d.sections) { notReady(); return; }
    S.data = d;
    var b = bannerEl();
    if (b) {
      var n = (d.sections.dynasty || []).length;
      // The stage phrase is a link: it is the only conversion route the page
      // carries outside the nav dropdown's last item.
      // The build date is the vintage line. "Free" is said only while the gate
      // is off, so the day the flag flips this banner stops claiming it.
      var built = String(d.generated_at || "").slice(0, 10);
      var D = gate(), gatingOn = false;
      try { gatingOn = !!(D && D.gating && D.gating()); } catch (e) { gatingOn = false; }
      b.innerHTML = '<div class="dyn-asof">' + n + " prospects · eFV board grades · " +
        esc(d.season || "") + " season" + (built ? " · built " + esc(built) : "") +
        ' · <a class="dyn-name-link" href="/diamond/">Diamond' + (gatingOn ? "" : " preview") + "</a>" +
        (gatingOn ? "" : ", free") + "</div>";
    }
    readHash();
    attachCard();
    wireTabs();
    syncTabs();
    renderSection();
    writeHash();
    syncCard();
  }
  // The lamp loader goes up before the payload is asked for, so a held or slow
  // load shows the loading kind rather than an empty root.
  function boot() {
    var r = root();
    if (r) r.innerHTML = pxState("loading", "Loading the Dynasty board.");
    load(DATA_URL).then(onData).catch(function (e) { errorState(String(e && e.message || e)); });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
  // Membership resolves AFTER first paint (the account layer is deferred and
  // async), so the helper's entitlement callback re-renders whichever board is
  // up when the answer lands or changes. Guarded on S.data: before the payload
  // there is nothing to cap. With gating off this fires once and re-renders
  // an identical board, which is cheap and keeps the seam exercised.
  (function () {
    var D = gate();
    if (D && D.onEntitlement) D.onEntitlement(function () { if (S.data) renderSection(); });
  })();

  // ---- module styles (theme tokens only, corners already sharpened site-wide)
  var css = document.createElement("style");
  css.textContent = [
    ".dyn-lensbar{display:flex;flex-wrap:wrap;align-items:center;gap:6px;margin:10px 0}",
    ".dyn-lens-lbl{font:600 11px/1 var(--font-retro,monospace);color:var(--text-tertiary);text-transform:uppercase;letter-spacing:.04em}",
    ".dyn-lens-note{flex:1 1 260px;font-size:12px;color:var(--text-secondary)}",
    ".dyn-lensbtn,.dyn-btn{font:600 12px/1 var(--font-retro,monospace);padding:6px 11px;border:1px solid var(--border);background:var(--bg-secondary);color:var(--text-secondary);cursor:pointer}",
    ".dyn-lensbtn.active{background:var(--accent-cyan);color:var(--text-on-accent);border-color:transparent}",
    ".dyn-tools{display:flex;justify-content:flex-end;margin:6px 0}",
    ".dyn-filterbar{display:flex;flex-wrap:wrap;align-items:center;gap:6px;margin:8px 0 2px}",
    ".dyn-f-q{padding:6px 8px;border:1px solid var(--border);background:var(--bg-primary);color:var(--text-primary);font:600 12px/1 var(--font-retro,monospace);min-width:170px}",
    ".dyn-f-chip{font:600 11px/1 var(--font-retro,monospace);padding:6px 9px;border:1px solid var(--border);background:var(--bg-secondary);color:var(--text-secondary);cursor:pointer}",
    ".dyn-f-chip.active{background:var(--accent-cyan);color:var(--text-on-accent);border-color:transparent}",
    ".dyn-filterbar select{padding:6px 8px;border:1px solid var(--border);background:var(--bg-primary);color:var(--text-primary);font:600 12px/1 var(--font-retro,monospace)}",
    ".dyn-f-count{font-size:11px;color:var(--text-tertiary)}",
    ".dyn-table{width:100%;border-collapse:collapse;font-size:13px;margin-top:8px}",
    ".dyn-table th{text-align:right;font:600 11px/1 var(--font-retro,monospace);color:var(--text-tertiary);text-transform:uppercase;letter-spacing:.03em;padding:6px 8px;border-bottom:1px solid var(--border)}",
    ".dyn-table td{text-align:right;padding:6px 8px;border-bottom:1px solid var(--border-light);color:var(--text-primary)}",
    // The name column is column 2 on the keeper table and column 1 on Call-up
    // Watch, so the old `th:nth-child(2)` left-aligned the WRONG heading on
    // each: "Prospect" sat right-aligned over left-aligned names and "Org" sat
    // left-aligned over right-aligned orgs. The heading now carries the same
    // class its cells do, which cannot drift when a column moves.
    ".dyn-table th.dyn-nm,.dyn-table td.dyn-nm{text-align:left}",
    // Wide tables scroll INSIDE this box. Without it the 7-column keeper table
    // measured 430px against a 390px phone and scrolled the PAGE sideways.
    ".dyn-tablewrap{max-width:100%}",
    "@media (max-width:640px){.dyn-tablewrap{scrollbar-width:thin;scrollbar-color:var(--border) transparent;padding-bottom:4px}",
    ".dyn-tablewrap::-webkit-scrollbar{height:4px;display:block}",
    ".dyn-tablewrap::-webkit-scrollbar-thumb{background:var(--border);border-radius:2px}}",
    // The keeper table's rank cell carries the SHARED rank class now (see the
    // note at its markup), so the muted colour is re-declared against it.
    ".dyn-table td.mlbstats-col-rank{color:var(--text-tertiary)}",
    ".dyn-table td.dyn-sc{font-weight:700}",
    ".dyn-pos{color:var(--accent-green)}.dyn-neg{color:var(--accent-red)}",
    ".dyn-note{font-size:12.5px;color:var(--text-secondary);background:var(--bg-secondary);border:1px solid var(--border);padding:9px 12px;margin:8px 0}",
    ".dyn-asof{font-size:12px;color:var(--text-tertiary);margin:4px 0}",
    ".dyn-error{border:1px solid var(--accent-red);padding:12px;color:var(--text-primary);background:var(--bg-secondary)}",
    ".dyn-name-link{color:var(--accent-cyan);text-decoration:none}.dyn-name-link:hover{text-decoration:underline}",
    ".dyn-tier{font:600 10px/1 var(--font-retro,monospace);color:var(--text-secondary);background:var(--bg-secondary);border:1px solid var(--border);padding:2px 6px;white-space:nowrap}",
    ".dyn-tier.dyn-tier-elite{color:var(--text-on-accent);background:var(--accent-green);border-color:transparent}",
    ".dyn-tier.dyn-tier-one{color:var(--accent-cyan);border-color:var(--accent-cyan)}",
    ".dyn-win{font:600 10px/1 var(--font-retro,monospace);border:1px solid var(--border);padding:1px 4px;white-space:nowrap}",
    ".dyn-win-in{color:var(--accent-green);border-color:var(--accent-green)}",
    ".dyn-win-out{color:var(--text-tertiary)}",
    ".dyn-form{display:flex;flex-wrap:wrap;gap:10px;align-items:flex-end;margin:10px 0}",
    ".dyn-field{display:flex;flex-direction:column;gap:3px;font:600 11px/1.3 var(--font-retro,monospace);color:var(--text-tertiary);text-transform:uppercase;letter-spacing:.03em}",
    ".dyn-field input{width:150px;padding:6px 8px;border:1px solid var(--border);background:var(--bg-primary);color:var(--text-primary);font:600 13px/1 var(--font-retro,monospace)}"
    // NOTHING FOR THE SORT BAR, THE RANK CHIP OR THE SCORE CELL LIVES HERE any
    // more. Those are .ff-sortbar / .ff-rank / .ff-strong in assets/site.css
    // and the markup above names them. The local copies that used to sit here
    // were at the same specificity but LATER in the cascade than the
    // stylesheet, so they quietly beat it: that is how the phone sort-bar
    // swipe strip and the rank diamond went missing on this page.
  ].join("");
  document.head.appendChild(css);
})();
