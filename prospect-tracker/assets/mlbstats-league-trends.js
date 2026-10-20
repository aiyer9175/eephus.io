/* Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
 * Unauthorized copying of this file, via any medium is strictly prohibited
 * Proprietary and confidential
 * Written by Noah J. Dengler (@ARKNDJL), 2026 */

// /mlbstats/ Trends tab (League Trends plan 4.1 to 4.5), lazy: mlbstats.js
// injects this on first open from data-trends-src (live flag only). Descriptive:
// a direction is words and a number, never a colour. Hash keys mview, mtype,
// mpos, mstr, mdir, msort (off-default only); the club is the shared team= key.
(function () {
  "use strict";
  var DASH = " - ";
  var VIEWS = ["players", "teams", "league"];
  var TYPES = [["velocity", "Velocity"], ["shape", "Pitch shape"], ["mix", "Pitch mix"], ["role", "Role"],
    ["swing", "Swing"], ["new_pitch", "New pitch"], ["playing_time", "Playing time"]];
  var POS = ["SP", "RP", "C", "1B", "2B", "3B", "SS", "LF", "CF", "RF", "DH"];
  var STR = ["", "Cleared the bar", "Cleared by 1", "Cleared by 2"];
  var SORTS = { players: [["strength", "Strength"], ["newest", "Newest first"], ["name", "Name"]],
    teams: [["club", "Club"], ["count", "Listed changes"]] };
  var NEW = { view: "players", type: "", pos: "", str: "", dir: "", sort: "", q: "" };
  var S = Object.assign({}, NEW);
  var CTX = null, DATA = null, STATE = "", SERIES = null, SSTATE = "", bound = null;
  var started = false;
  function esc(s) {
    return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }
  function isN(v) { return v != null && v !== "" && typeof v !== "boolean" && isFinite(v); }
  function f1(v, d) { return isN(v) ? Number(v).toFixed(d == null ? 1 : d) : DASH; }
  function sgn(v) { var s = f1(v); return isN(v) && Number(s) > 0 ? "+" + s : s; }
  function rate3(v) { return isN(v) ? Number(v).toFixed(3).replace(/^0\./, ".") : DASH; }
  function monDay(iso) {
    var m = /^\d{4}-(\d\d)-(\d\d)/.exec(iso || "");
    return m ? "JanFebMarAprMayJunJulAugSepOctNovDec".substr((m[1] - 1) * 3, 3) + " " + Number(m[2]) : (iso || "");
  }
  function dayNum(iso) { var d = Date.parse(iso); return isNaN(d) ? null : d / 864e5; }
  function typeLabel(t) {
    var r = TYPES.filter(function (x) { return x[0] === t; })[0];
    return r ? r[1] : String(t || "");
  }
  function team() { return CTX && CTX.team ? CTX.team() : ""; }
  var RE = {
    view: /(?:^#|[#&])mview=(players|teams|league)\b/, type: /(?:^#|[#&])mtype=([a-z_]+)\b/,
    pos: /(?:^#|[#&])mpos=([A-Z0-9]{1,3})\b/, str: /(?:^#|[#&])mstr=([1-3])\b/,
    dir: /(?:^#|[#&])mdir=(up|down)\b/, sort: /(?:^#|[#&])msort=([a-z]+)\b/
  };
  function sortList() { return SORTS[S.view === "teams" ? "teams" : "players"]; }
  function sortOf() { return S.sort || sortList()[0][0]; }
  function readHash(h) {
    var m;
    if ((m = RE.view.exec(h))) S.view = m[1];
    if ((m = RE.type.exec(h)) && typeLabel(m[1]) !== m[1]) S.type = m[1];
    if ((m = RE.pos.exec(h)) && POS.indexOf(m[1]) >= 0) S.pos = m[1];
    if ((m = RE.str.exec(h))) S.str = m[1];
    if ((m = RE.dir.exec(h))) S.dir = m[1];
    if ((m = RE.sort.exec(h)) && sortList().some(function (x) { return x[0] === m[1]; })) S.sort = m[1];
  }
  function hashParts() {
    var p = [];
    if (S.view !== NEW.view) p.push("mview=" + S.view);
    if (S.type) p.push("mtype=" + S.type);
    if (S.pos) p.push("mpos=" + S.pos);
    if (S.str) p.push("mstr=" + S.str);
    if (S.dir) p.push("mdir=" + S.dir);
    if (S.view !== "league" && sortOf() !== sortList()[0][0]) p.push("msort=" + sortOf());
    return p;
  }
  function getJSON(url, done) {
    try {
      fetch(url, { cache: "no-cache" })
        .then(function (r) { return (r && r.ok) ? r.json() : null; })
        .then(function (j) { done(j || null); }, function () { done(null); });
    } catch (e) { done(null); }
  }
  function load() {
    if (STATE) return;
    STATE = "loading";
    getJSON("/data/league_trends.json", function (j) {
      DATA = (j && j.players && j.families) ? j : null;
      STATE = DATA ? "ok" : "error";
      if (CTX && CTX.active()) render();
    });
  }
  function loadSeries() {
    if (SSTATE) return;
    SSTATE = "loading";
    getJSON("/data/mlb_league_series.json", function (j) {
      SERIES = (j && j.seasons) ? j : null;
      SSTATE = SERIES ? "ok" : "error";
      if (CTX && CTX.active() && S.view === "league") render();
    });
  }
  var EV = { rotation: "Rotation", new_pitch: "New pitch", playing_time: "Playing time" };
  function items() {
    var out = [];
    (DATA.players || []).forEach(function (p) {
      out.push({ card: 1, id: p.id, name: p.name, club: p.club, pos: p.pos, type: p.type,
        dirw: p.dir > 0 ? "up" : "down", str: p.strength, date: p.first_flagged, row: p });
    });
    (DATA.events || []).forEach(function (e) {
      var d = e.direction;
      out.push({ id: e.id, name: e.name, club: e.club, pos: e.pos, type: e.rule === "rotation" ? "role" : e.rule,
        dirw: /^(into|in)$/.test(d) ? "up" : (/^out/.test(d || "") ? "down" : ""), str: 0, date: e.date, row: e });
    });
    return out;
  }
  function passes(it) {
    return (!team() || it.club === team()) && (!S.type || it.type === S.type) && (!S.pos || it.pos === S.pos)
      && (!S.str || (it.card && it.str >= Number(S.str))) && (!S.dir || it.dirw === S.dir)
      && (!S.q || String(it.name || "").toLowerCase().indexOf(S.q.toLowerCase()) >= 0);
  }
  function cmp(a, b) { return a < b ? -1 : (a > b ? 1 : 0); }
  function sortItems(list) {
    var k = sortOf(), nm = function (x) { return String(x.name || "~"); };
    return list.sort(function (a, b) {
      if (k === "name") return cmp(nm(a), nm(b));
      var d = cmp(String(b.date), String(a.date));
      return (k === "newest" ? 0 : b.str - a.str) || d || cmp(nm(a), nm(b));
    });
  }
  function hostW() {
    var h = CTX && CTX.host ? CTX.host() : null, w = Number(h && h.clientWidth);
    return w > 0 ? w : 1232;
  }
  function cardW() {
    var w = hostW(), cols = w >= 740 ? 2 : 1;
    return Math.max(150, Math.min(520, Math.round((w - (cols - 1) * 10) / cols - 22)));
  }
  function sparkSVG(sp, unit) {
    var H = window.EEPHUS_HUB, v = sp && sp.v ? sp.v.filter(isN).map(Number) : [];
    if (!H || !H.spark || v.length < 2) return "";
    // X and Y mirror EEPHUS_HUB.spark's padding (3 across, 6 down)
    var W = cardW(), HT = 46, all = v.concat(isN(sp.base) ? [Number(sp.base)] : []);
    var lo = Math.min.apply(null, all), hi = Math.max.apply(null, all);
    var svg = H.spark(v.map(function (x, i) { return { y: i, v: x }; }), { width: W, height: HT, lo: lo, hi: hi,
      aria: "Last " + v.length + " values, " + f1(v[0]) + " to " + f1(v[v.length - 1]) + " " + unit });
    var X = function (i) { return (3 + i * (W - 6) / (v.length - 1)).toFixed(1); };
    var Y = function (x) { return (6 + (hi - x) * (HT - 12) / ((hi - lo) || 1)).toFixed(1); };
    var add = isN(sp.base) ? '<line x1="3" x2="' + (W - 3) + '" y1="' + Y(sp.base) + '" y2="' + Y(sp.base)
      + '" stroke="var(--text-tertiary)" stroke-dasharray="4 3"/>' : "";
    for (var i = v.length - Math.min(v.length, Math.max(1, Number(sp.w) || 1)); i < v.length; i++) {
      add += '<circle cx="' + X(i) + '" cy="' + Y(v[i]) + '" r="3" fill="var(--viz-1)"/>';
    }
    return svg.replace(/<\/svg>\s*$/, add + "</svg>");
  }
  function sel(key, label, opts, cur) {
    return '<label class="mlbstats-ctl">' + label + ' <select id="mlbx-tr-' + key + '" data-trf="' + key + '" aria-label="Filter by '
      + label + '">' + opts.map(function (o) {
        return '<option value="' + esc(o[0]) + '"' + (o[0] === cur ? " selected" : "") + ">" + esc(o[1]) + "</option>";
      }).join("") + "</select></label>";
  }
  function clubs() {
    var seen = {};
    [DATA.players, DATA.events, DATA.teams].forEach(function (a) { (a || []).forEach(function (r) { if (r.club) seen[r.club] = 1; }); });
    return Object.keys(seen).sort();
  }
  function bar() {
    if (S.view === "league") return "";
    var all = (S.view === "players");
    var n = (team() ? 1 : 0) + (S.type ? 1 : 0) + (S.pos ? 1 : 0) + (S.str ? 1 : 0) + (S.dir ? 1 : 0);
    var cl = [["", "All teams"]].concat(clubs().map(function (c) { return [c, c]; }));
    return '<div class="' + CTX.filtCls() + '">'
      + (all ? '<input class="mlbstats-search" type="search" id="mlbx-tr-q" placeholder="Search a player" value="' + esc(S.q)
        + '" aria-label="Search a player">' : "") + CTX.filtBtn(all ? n : (team() ? 1 : 0))
      + sel("team", "team", cl, team())
      + (all ? sel("pos", "position", [["", "All positions"]].concat(POS.map(function (p) { return [p, p]; })), S.pos)
        + sel("type", "type", [["", "All types"]].concat(TYPES), S.type)
        + sel("str", "strength", [["", "Any strength"], ["1", STR[1]], ["2", "Cleared by 1 or more"], ["3", "Cleared by 2 or more"]], S.str)
        + sel("dir", "direction", [["", "Up or down"], ["up", "Up"], ["down", "Down"]], S.dir) : "")
      + sel("sort", "sort", sortList(), sortOf()) + "</div>";
  }
  function banner(d) {
    var notes = [], a = dayNum(d.as_of), b = dayNum(d.boards_last_game), ps = d.players || [];
    if (d.mode === "final") {
      notes.push("The " + d.season + " regular season ended " + monDay(d.as_of) + ". These are the changes over its final weeks.");
    } else if (a != null && b != null && b - a > (isN(d.max_lag_days) ? Number(d.max_lag_days) : 2)) {
      notes.push("Not updated since " + monDay(d.as_of) + ": later games are not in yet.");
    }
    if (ps.length && ps.every(function (p) { return p.mode === "prior_season"; })) {
      notes.push("The list starts after each pitcher's first 3 starts or 6 outings, measured against " + (d.season - 1) + ".");
    }
    return CTX.bannerHTML(d) + notes.map(function (t) { return '<div class="mlbstats-note mlbx-trnote">' + esc(t) + "</div>"; }).join("");
  }
  function fold(d) {
    var m = d.method || {}, n = (d.players || []).length + (d.events || []).length;
    return '<div class="mlbstats-note">' + n + " listed " + (n === 1 ? "change" : "changes") + " as of " + esc(monDay(d.as_of))
      + (isN(m.false_per_day) ? "; about " + f1(m.false_per_day, 2) + " of them expected from game-to-game noise alone." : ".")
      + '</div><details class="mlbx-trfold"><summary>How changes are listed</summary><p>' + esc(m.fold) + "</p></details>";
  }
  function dots(n) {
    var s = "";
    for (var i = 1; i <= 3; i++) s += '<i class="mlbx-trdot' + (i <= n ? " is-on" : "") + '"></i>';
    return '<span class="mlbx-trdots" role="img" aria-label="' + STR[n] + '">' + s + "</span> " + STR[n];
  }
  function clubChip(c) {
    var H = window.EEPHUS_HUB;
    return H && H.clubLinkHTML && c ? H.clubLinkHTML(c, { text: "code" }) : esc(c);
  }
  function playerHref(it) { return CTX.playerHref ? CTX.playerHref({ mlbam: it.row.mlbam }) : null; }
  function nameHTML(it) {
    var nm = esc(it.name || "Player " + it.row.mlbam), h = playerHref(it);
    return h ? '<a href="' + esc(h) + '">' + nm + "</a>" : nm;
  }
  function contextLine(c) {
    var o = c && c.obp_30d, k = c && c.k_bb_30d, b = [];
    if (!c) return "";
    if (c.index && isN(c.index.value)) b.push(esc(c.index.label) + " " + esc(c.index.value) + " this season");
    if (o) b.push("30-day OBP " + rate3(o.window) + " against " + rate3(o.before) + " earlier (" + o.pa_window + " and " + o.pa_before + " PA)");
    if (k) b.push("30-day K-BB% " + f1(k.window) + " against " + f1(k.before) + " earlier (" + k.bf_window + " and " + k.bf_before + " batters faced)");
    return b.length ? '<div class="mlbx-trctx"><b>Context:</b> ' + b.join("; ") + ". " + esc(c.note) + "</div>" : "";
  }
  function linksHTML(it) {
    var r = it.row, l = r.links || {}, H = window.EEPHUS_HUB, h = playerHref(it), fr = H && H.clubHref && r.club ? H.clubHref(r.club) : "";
    var a = [h ? ["Player page", h] : 0, l.board ? ["Open in the board", l.board, 1] : 0, fr ? ["Franchise page", fr] : 0,
      l.pal ? ["Alchemy Lab section", l.pal] : 0].filter(Boolean).map(function (x) {
      return '<a href="' + esc(x[1]) + '"' + (x[2] ? ' data-trboard="' + esc(x[1]) + '"' : "") + ">" + x[0] + "</a>";
    });
    return a.length ? '<div class="mlbx-trlinks">' + a.join(" ") + "</div>" : "";
  }
  function cell(k, v) { return "<div><dt>" + k + "</dt><dd>" + v + "</dd></div>"; }
  function head(it, sub, meta) {
    return "<header><h3>" + nameHTML(it) + "</h3> " + clubChip(it.club) + ' <span class="proj-dim">' + meta + '</span></header><div class="mlbx-trtype">'
      + sub + "</div>";
  }
  function cardHTML(it) {
    var p = it.row, u = " " + esc(p.unit || ""), w = p.window || {}, b = p.baseline || {};
    var fam = ((DATA.families || []).filter(function (f) { return f.key === p.family; })[0] || {}).label;
    return '<article class="mlbx-trcard">' + head(it, esc(typeLabel(p.type)) + (fam ? " &middot; " + esc(fam) : "") + " &middot; " + dots(p.strength),
        esc(it.pos) + (p.mode === "prior_season" ? " &middot; measured against last season" : ""))
      + '<p class="mlbx-trsent">' + esc(p.sentence) + '</p><dl class="mlbx-trnums">'
      + cell("Window", f1(w.value) + u + " (n " + w.n + ")") + cell("Earlier", f1(b.value) + u + " (n " + b.n + ")")
      + cell("Change", sgn(p.change) + u) + cell("League drift", sgn(p.drift) + u) + cell("Net of league", sgn(p.net) + u)
      + (isN(p.shrunk) ? cell("Shrunk toward no change for game-to-game noise", sgn(p.shrunk) + u) : "")
      + cell("Cleared", "bar " + f1(p.bar, 2) + " at " + f1(Math.abs(p.z))) + cell("First flagged", esc(p.first_flagged)) + "</dl>"
      + '<div class="mlbx-trspark">' + sparkSVG(p.spark, p.unit || "") + (p.spark
        ? '<div class="mlbx-trsparkkey proj-dim">Last ' + (p.spark.v || []).length + " values; filled points are the window; dashed line is the earlier mean</div>" : "")
      + "</div>" + contextLine(p.context) + linksHTML(it) + "</article>";
  }
  function eventHTML(it) {
    var e = it.row;
    return '<article class="mlbx-trcard">' + head(it, esc(EV[e.rule] || typeLabel(e.type)) + " &middot; a rule, not a measured change",
        esc(it.pos) + " &middot; through " + esc(monDay(e.date))) + '<p class="mlbx-trsent">' + esc(e.sentence) + "</p>" + linksHTML(it) + "</article>";
  }
  function playersOut() {
    var list = sortItems(items().filter(passes));
    if (!list.length) {
      return '<div class="mlbstats-empty">No listed changes for this filter. <button type="button" class="chip" data-trclear="1">Clear filters</button></div>';
    }
    return '<div class="mlbx-trgrid">' + list.map(function (it) { return it.card ? cardHTML(it) : eventHTML(it); }).join("") + "</div>";
  }
  function strip(r, k) {
    var a = r["l" + k], b = r["before_l" + k], band = r["band_l" + k];
    if (!a || !b || !isN(a.rd) || !isN(b.rd)) return "";
    var W = Math.max(150, Math.min(320, cardW() - 40)), X = function (v) { return (4 + (Math.max(-6, Math.min(6, v)) + 6) * (W - 8) / 12).toFixed(1); };
    var bd = isN(band) ? '<rect x="' + X(b.rd - band) + '" y="5" width="' + Math.max(1, X(b.rd + band) - X(b.rd - band)).toFixed(1)
      + '" height="12" fill="var(--bg-tertiary)" stroke="var(--border)"/>' : "";
    return '<div class="mlbx-trrd"><div class="mlbx-trrdh">Last ' + k + " games: " + sgn(a.rd) + " runs a game (" + f1(a.rs) + " scored, "
      + f1(a.ra) + " allowed) against " + sgn(b.rd) + " before" + (isN(band) ? "; chance band " + String.fromCharCode(177) + f1(band) : "")
      + '</div><svg class="eephus-chart" viewBox="0 0 ' + W + ' 22" style="display:block;width:100%;height:auto" role="img" aria-label="Run differential a game, last '
      + k + '">' + bd + '<line x1="' + X(b.rd) + '" x2="' + X(b.rd)
      + '" y1="3" y2="19" stroke="var(--text-tertiary)"/><circle cx="' + X(a.rd) + '" cy="11" r="3.4" fill="var(--viz-1)"/></svg></div>';
  }
  function penLine(p) {
    var rows = [3, 7].filter(function (d) { return isN(p && p["relief_outs_" + d + "d"]); }).map(function (d) {
      var o = p["relief_outs_" + d + "d"], k = "relief_outs_" + d + "d";
      return "<li>Last " + d + " days: " + Math.floor(o / 3) + "." + (o % 3) + " relief innings, " + p["relief_pitches_" + d + "d"]
        + " pitches; rank " + p[k + "_rank"] + " of 30 on innings (median club " + f1(p[k + "_median"] / 3) + ")</li>";
    });
    return rows.length ? '<ul class="mlbx-trpen"><li class="proj-dim">Bullpen workload, a count and a rank</li>' + rows.join("") + "</ul>" : "";
  }
  function clubBtn(c, label, n) {
    return '<button type="button" class="chip" data-trclub="' + esc(c) + '">' + esc(label) + (n ? ' <span class="proj-dim">' + n + "</span>" : "") + "</button>";
  }
  function teamsOut() {
    var ts = DATA.teams || [], all = items(), count = {}, byId = {};
    all.forEach(function (it) { byId[it.id] = it; if (it.club) count[it.club] = (count[it.club] || 0) + 1; });
    if (!ts.length) {
      var cs = Object.keys(count).sort(function (a, b) { return count[b] - count[a] || cmp(a, b); });
      return '<div class="mlbstats-empty">' + esc(DATA.teams_note || "The Teams view is not computed yet.") + "</div>"
        + (cs.length ? '<h3 class="mlbx-trh">Listed changes by club</h3><div class="mlbx-trchips">'
          + cs.map(function (c) { return clubBtn(c, c, count[c]); }).join("") + "</div>" : "");
    }
    var k = sortOf();
    var n = function (t) { return (t.card_ids || []).length + (t.event_ids || []).length; };
    var list = ts.filter(function (t) { return !team() || t.club === team(); }).sort(function (a, b) {
      return (k === "count" ? n(b) - n(a) : 0) || cmp(a.club, b.club);
    });
    if (!list.length) return '<div class="mlbstats-empty">No club matches this filter.</div>';
    return '<div class="mlbx-trgrid">' + list.map(function (t) {
      var chips = (t.card_ids || []).concat(t.event_ids || []).map(function (id) {
        return byId[id] ? clubBtn(t.club, byId[id].name || "Player " + byId[id].row.mlbam) : "";
      }).join("");
      return '<article class="mlbx-trcard"><header><h3>' + clubChip(t.club) + "</h3></header>"
        + (t.sentence ? '<p class="mlbx-trsent">' + esc(t.sentence) + "</p>" : "") + strip(t.rd, 10) + strip(t.rd, 30)
        + penLine(t.pen) + '<div class="mlbx-trchips">' + (chips || '<span class="proj-dim">No listed player changes.</span>') + "</div></article>";
    }).join("") + "</div>";
  }
  function refOf(c) {
    var m = /#(hit|pit|team)\/([a-z0-9_]+)$/.exec(c.series_ref || "");
    return m ? { side: m[1], stat: m[2] } : null;
  }
  function leaguePts(c) {
    var pts = [], ref = refOf(c);
    if (c.values) {
      Object.keys(c.values).sort().forEach(function (y) {
        pts.push({ y: y, v: Number(c.values[y]), partial: (c.completed || []).indexOf(y) < 0 });
      });
    } else if (ref && SERIES) {
      var cell = ref.side === "hit" || ref.stat === "sp_ip_per_gs" ? "all" : "pitchers_only";
      Object.keys(SERIES.seasons).sort().forEach(function (y) {
        var s = SERIES.seasons[y] || {}, blk = (s[ref.side] || {})[cell];
        if (blk && isN(blk[ref.stat]) && (s.complete || !c.completed_only)) {
          pts.push({ y: y, v: Number(blk[ref.stat]) * (/^percent/.test(c.unit) ? 100 : 1), partial: !s.complete });
        }
      });
    }
    return pts;
  }
  function leagueCard(c) {
    var pts = leaguePts(c), H = window.EEPHUS_HUB, d = isN(c.decimals) ? c.decimals : 2, ref = refOf(c), last = pts[pts.length - 1];
    var sp = H && H.spark && pts.length > 1 ? H.spark(pts, { xs: pts.map(function (p) { return p.y; }), width: cardW(), height: 46, last: true,
      aria: c.label + " by season, " + pts[0].y + " to " + last.y }) : "";
    return '<article class="mlbx-trcard"><header><h3>' + esc(c.label) + "</h3> "
      + (c.notable ? '<span class="mlbx-trnotable">Notable: ' + esc((c.notable_why || []).join("; ") || "by the rule") + "</span>" : "")
      + '</header><p class="mlbx-trsent">' + esc(c.sentence) + '</p><dl class="mlbx-trnums">'
      + cell(c.season + (c.complete ? "" : " to date"), f1(c.value, d)) + cell(c.prev_season, f1(c.prev, d))
      + cell("Five-season mean", f1(c.mean5, d)) + '</dl><div class="mlbx-trspark">' + sp
      + (sp ? '<div class="mlbx-trsparkkey proj-dim">' + pts[0].y + " to " + last.y + (last.partial ? "; the last point is a season in progress" : "") + "</div>" : "")
      + '</div><div class="proj-dim">' + (c.run ? "A run of " + c.run + " " + (c.run === 1 ? "season" : "seasons") + " in the same direction. " : "")
      + "Notable rule: " + esc(c.notable_rule) + (c.source ? ". Source: " + esc(c.source) : "") + "</div>"
      + (c.footnote ? '<div class="mlbx-trfoot proj-dim">' + esc(c.footnote) + "</div>" : "")
      + (ref && CTX.gotoLeague ? '<div class="mlbx-trlinks"><a href="#section=league&gview=time&gside=' + ref.side + "&gstat=" + esc(ref.stat)
        + '" data-trleague="' + esc(ref.side + "/" + ref.stat) + '">See it over time</a></div>' : "") + "</article>";
  }
  function leagueOut() {
    var cards = DATA.league || [];
    if (!cards.length) return '<div class="mlbstats-empty">No league cards.</div>';
    if (cards.some(refOf)) loadSeries();
    return (SSTATE === "error" ? '<div class="mlbstats-note">The season series did not load, so some cards show no chart.</div>' : "")
      + '<div class="mlbx-trgrid">' + cards.map(leagueCard).join("") + "</div>";
  }
  function out() { return S.view === "teams" ? teamsOut() : S.view === "league" ? leagueOut() : playersOut(); }
  function render() {
    var host = CTX && CTX.host ? CTX.host() : null;
    if (!host) return;
    if (!STATE || STATE === "loading") { host.innerHTML = CTX.pxState("loading", "Loading the Trends tab."); load(); return; }
    if (STATE === "error") {
      host.innerHTML = CTX.pxState("failed", "The Trends tab did not load. "
        + '<button type="button" class="chip" data-trretry="1">Retry</button>', "mlbstats-load-error");
      return;
    }
    host.innerHTML = banner(DATA) + '<div class="mlbstats-seasons" role="group" aria-label="Trends view">' + VIEWS.map(function (v) {
      return '<button type="button" class="mlbstats-season' + (S.view === v ? " active" : "") + '" data-trview="' + v
        + '" aria-pressed="' + (S.view === v) + '">' + v.charAt(0).toUpperCase() + v.slice(1) + "</button>";
    }).join("") + "</div>" + fold(DATA) + bar() + '<div id="mlbx-tr-out">' + out() + "</div>";
    if (CTX.wireGlossary) CTX.wireGlossary(host);
  }
  function save() { if (CTX && CTX.writeHash) CTX.writeHash(); }
  function setFilter(k, v) { if (k === "team") CTX.setTeam(v); else S[k] = v; }
  function act(t) {
    var a, g = function (n) { return t.getAttribute(n); };
    if ((a = g("data-trview"))) { if (VIEWS.indexOf(a) >= 0) { S.view = a; S.sort = ""; save(); render(); } }
    else if ((a = g("data-trclub"))) { CTX.setTeam(a); S.view = "players"; S.sort = ""; save(); render(); }
    else if (g("data-trclear")) { S.type = S.pos = S.str = S.dir = S.q = ""; CTX.setTeam(""); save(); render(); }
    else if (g("data-trretry")) { STATE = ""; DATA = null; render(); }
    else if ((a = g("data-trleague"))) { if (CTX.gotoLeague) CTX.gotoLeague.apply(null, a.split("/")); }
    else if ((a = g("data-trboard"))) {
      var m = /section=([a-z]+)&player=(\d+)/.exec(a);
      if (m && CTX.openBoard) CTX.openBoard(m[1], m[2]);
    }
  }
  function onClick(e) {
    var t = e.target && e.target.closest ? e.target.closest("[data-trview],[data-trclub],[data-trclear],[data-trretry],[data-trleague],[data-trboard]") : null;
    if (!t) return;
    if ((t.getAttribute("data-trboard") && CTX.openBoard) || (t.getAttribute("data-trleague") && CTX.gotoLeague)) e.preventDefault();
    act(t);
  }
  function onChange(e) {
    var k = e.target && e.target.getAttribute ? e.target.getAttribute("data-trf") : null;
    if (!k) return;
    setFilter(k, e.target.value);
    save(); render();
  }
  function onInput(e) {
    if (!e.target || e.target.id !== "mlbx-tr-q") return;
    S.q = String(e.target.value || "");
    var el = document.getElementById("mlbx-tr-out");
    if (el) el.innerHTML = out(); else render();
  }
  function show(ctx) {
    CTX = ctx;
    if (!started) {
      started = true;
      try { readHash(location.hash || ""); } catch (e) { /* none */ }
    }
    var host = CTX.host();
    if (host && bound !== host) {
      bound = host;
      host.addEventListener("click", onClick);
      host.addEventListener("change", onChange);
      host.addEventListener("input", onInput);
    }
    render();
  }
  window.MLBX_TRENDS = {
    show: show, hashParts: hashParts, readHash: readHash, render: render,
    _state: function () { return JSON.parse(JSON.stringify(S)); },
    _reset: function () { S = Object.assign({}, NEW); },
    _filter: function (k, v) { setFilter(k, v); save(); render(); },
    _act: function (a) { act({ getAttribute: function (n) { return a[n] != null ? a[n] : null; } }); }
  };
  try {
    var want = window.MLBX_TRENDS_CTX, c = typeof want === "function" ? want() : null;
    if (c && c.active && c.active()) show(c);
  } catch (e) { /* retried on show */ }
})();
