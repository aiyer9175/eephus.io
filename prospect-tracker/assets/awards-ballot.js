/* eephus.io /awards/ My Ballot (AWARDS_9, AWARDS_PLAN 5.8): never filled from, scored or counted against anyone. */
(() => {
"use strict";
var LS = "eephus.awards.ballot.v1";
var KEYS = ["al-mvp", "nl-mvp", "al-cy", "nl-cy", "al-roy", "nl-roy", "al-moy", "nl-moy"];
var AWD = { mvp: "MVP", cy: "CY", roy: "ROY", moy: "MOY" };
var FULL = { MVP: "MVP", CY: "Cy Young", ROY: "Rookie of the Year", MOY: "Manager of the Year" };
var NOTE = {
  ok: "Saved in this browser only. Nothing is sent to eephus.io; there is no account behind this page. " +
    "A private window or clearing site data erases it. To keep it, copy the link",
  no: "This browser is not saving your ballot (private window or blocked storage). It lasts until you " +
    "leave the page; copy the link to keep it."
};
var FLAGS = { id: 1, name: 1, club: 1, pos: 1, place: 1, below_floor: 1, outside_rookie_proxy: 1, two_way: 1 };
var TAIL = { age: 1, pa: 1, ip: 1 };
var PIT = /^(P|SP|RP)$/, DOT = " \u00b7 ", T = window.EephusTiers || null;
var store = { seasons: {}, showSelection: true }, storage = "ok", timer = null, cands = {};
var ui = { active: "al-mvp", q: "", target: null, opt: -1, list: false, sort: {}, floor: {}, side: "all", every: false,
           drawer: null, from: null, confirm: false };
var shared = null, cx = null, P = null, S = null, C = null, D = null, M = null, pv = {}, bp = "", rt = null;

(function read() {
  var raw = null;
  try { raw = window.localStorage.getItem(LS); } catch (e) { storage = "unavailable"; return; }
  try {
    var j = raw && JSON.parse(raw);
    if (j && j.v === 1 && j.seasons && typeof j.seasons === "object") {
      store.seasons = j.seasons;
      if (typeof j.showSelection === "boolean") store.showSelection = j.showSelection;
    }
  } catch (e) { /* starts empty; the stored value stays until an edit */ }
})();
function save() {
  clearTimeout(timer);
  timer = setTimeout(() => {
    var was = storage;
    try {
      window.localStorage.setItem(LS, JSON.stringify({ v: 1, seasons: store.seasons, showSelection: store.showSelection,
        updated: new Date().toISOString() }));
      storage = "ok";
    } catch (e) { storage = "unavailable"; }
    if (was !== storage) paintNote();
  }, 300);
}

// helpers
var esc = s => cx.esc(s), ord = n => cx.ord(n), el = id => document.getElementById("aw-b-" + id), ga = (t, a) => t.getAttribute("data-" + a);
function num(v) { var n = Number(v); return (v == null || v === "" || typeof v === "boolean" || !isFinite(n)) ? null : n; }
function fmt(v, d) { var n = num(v), s = n == null ? null : n.toFixed(d); return s && /^-0(\.0+)?$/.test(s) ? s.slice(1) : s; }
function awardOf(k) { return AWD[k.split("-")[1]]; }
function lgOf(k) { return k.split("-")[0].toUpperCase(); }
function title(k) { return lgOf(k) + " " + FULL[awardOf(k)]; }
function rule(A) { return (cx.main.ballot_rules || {})[A] || { n: 0, points: [] }; }
function mq(w) { return !!(window.matchMedia && window.matchMedia(`(min-width: ${w}px)`).matches); }
var wide = () => mq(768), two = () => mq(1200);
function focus(sel) { var n = P.querySelector(sel); if (n) n.focus(); return n; }
function norm(s) { return String(s == null ? "" : s).normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase(); }
function btn(act, label, extra, cls) { return `<button class="aw-b-btn${cls ? " " + cls : ""}" data-act="${act}"${extra || ""}>${label}</button>`; }
function sw(act, on, label) { return `<button class="aw-b-sw" role="switch" data-act="${act}" aria-checked="${on}">${label}</button>`; }
function sub(a) { return `<span class="aw-b-sub">${esc(a.filter(Boolean).join(DOT))}</span>`; }
var ST = (kind, msg) => cx.stateBox(kind, msg);
var none = () => say(`Your ${title(ui.active)} ballot is empty.`);
function say(msg) { var n = el("live"); if (n) n.textContent = msg + (n.textContent === msg ? "\u00a0" : ""); }
var moy = k => awardOf(k) === "MOY";
var who = k => moy(k) ? "club" : "player";
function label(k, r) { return moy(k) ? r.club : r.name + " (" + r.club + ")"; }

// the candidate file
function load(season) {
  if (cands[season]) return cands[season];
  var p = fetch("/data/awards_candidates_" + season + ".json", { credentials: "same-origin" })
    .then(r => r.ok ? r.json() : Promise.reject(r.status))
    .then(j => {
      if (!j || j.schema !== 1 || !j.pools || !j.columns || j.season !== season) throw new Error("schema");
      var out = { cols: j.columns, pools: {} };
      Object.keys(j.pools).forEach(k => {
        var p = j.pools[k], cols = j.columns[awardOf(k)] || [], by = {};
        var mk = (arr, x) => {
          var o = { v: {}, out: !!x, reason: x && x.reason };
          cols.forEach((c, i) => { o.v[c.key] = arr[i]; });
          o.id = String(o.v.id); o.name = o.v.name; o.club = o.v.club; o.pos = o.v.pos || "";
          return (by[o.id] = o);
        };
        out.pools[k] = { rows: (p.rows || []).map(r => mk(r)), out: (p.proxy_out || []).map(x => mk(x.row, x)), by: by };
      });
      return (cands[season] = out);
    });
  p.catch(() => { delete cands[season]; });
  return (cands[season] = p);
}
function row(k, id) { var p = C.pools[k]; return p && id != null ? p.by[id] || null : null; }
function meta() {
  var fam = {}, dec = {}, top = {}, tpl = {};
  Object.keys(D.awards || {}).forEach(A => Object.keys(D.awards[A] || {}).forEach(L => {
    var b = D.awards[A][L] || {}, t = top[L.toLowerCase() + "-" + A.toLowerCase()] = {};
    ((b.compare || {}).metrics || []).forEach(m => {
      if (m.key === "score") return;
      if (m.family) fam[m.key] = m.family;
      if (m.decimals != null) dec[m.key] = m.decimals;
    });
    (b.top || []).forEach(r => {
      var l = r.links || {}, id = r.mlbam != null ? String(r.mlbam) : r.club;
      t[r.mlbam != null ? id : "c" + String(id).toLowerCase()] = r;
      ["overview", "management", "franchise"].forEach(x => { if (l[x] && !tpl[x]) tpl[x] = l[x].split(id).join("{id}"); });
    });
  }));
  return { fam: fam, dec: dec, top: top, tpl: tpl };
}
function famOf(key, A) { return key === "score" ? ((D.rules || {})[A] || {}).family || null : M.fam[key] || null; }
function decOf(k, key) {
  var r = (D.rules || {})[awardOf(k)] || {};
  if (key === "score") return r.decimals == null ? 1 : r.decimals;
  if (M.dec[key] == null) M.dec[key] = C.pools[k] && C.pools[k].rows.some(x => num(x.v[key]) % 1) ? 2 : 0;
  return M.dec[key];
}
// a score on the rule's ballot prints its score_display
function show(k, r, key) {
  var t = key === "score" && M.top[k] && M.top[k][r.id];
  return fmt(t ? t.score_display : r.v[key], decOf(k, key));
}
function ink(v, fam) { return (T && fam) ? T.clsInk(v, fam) : ""; }
function poolVals(k, key) {
  if (pv[k + key]) return pv[k + key];
  var out = [];
  (C.pools[k] ? C.pools[k].rows : []).forEach(r => {
    var v = num(r.v[key]);
    if (r.v.below_floor !== true && v != null && !((key === "pa" || key === "ip") && v === 0)) out.push(v);
  });
  return (pv[k + key] = out.sort((a, b) => a - b));
}
// Mid-rank percentile in the pool above the rule's floor, ties shared.
function pct(v, vals) {
  if (v == null || !vals.length) return null;
  var lo = 0, eq = 0;
  vals.forEach(x => { if (x < v) lo++; else if (x === v) eq++; });
  return Math.round(1000 * (lo + 0.5 * eq) / vals.length) / 10;
}

// ballots and the link
function slots(k) {
  var n = rule(awardOf(k)).n, bs = store.seasons[S] = typeof store.seasons[S] === "object" && store.seasons[S] || {};
  var a = Array.isArray(bs[k]) ? bs[k] : [];
  if (a.length !== n || a.some(x => x != null && typeof x !== "string")) bs[k] = a = Array.from({ length: n }, (_, i) => a[i] == null ? null : String(a[i]));
  return a;
}
function filled(a) { return a.filter(x => x != null).length; }
function has(a) { return !!a && filled(a) > 0; }
function enc(only) {
  return KEYS.filter(k => !only || k === only).map(k => {
    var a = slots(k).slice();
    while (a.length && a[a.length - 1] == null) a.pop();
    return a.length ? k + ":" + a.map(id => id == null ? "_" : moy(k) ? id : Number(id).toString(36)).join(".") : null;
  }).filter(Boolean).join(",");
}
function url(b) { return `${location.origin}${location.pathname}#section=ballot&season=${S}&b=${b}`; }
// Unknown ids are dropped and counted; a duplicate keeps its first slot.
function parse(b) {
  var out = {}, dropped = 0;
  if (!/^[a-z0-9._:,-]+$/.test(b)) return null;
  b.split(",").forEach(part => {
    var i = part.indexOf(":"), key = i > 0 ? part.slice(0, i) : "", toks = part.slice(i + 1).split("."), arr = [], seen = {};
    if (KEYS.indexOf(key) < 0 || out[key]) { dropped += toks.filter(x => x && x !== "_").length; return; }
    var n = rule(awardOf(key)).n;
    for (var j = 0; j < n; j++) arr.push(null);
    toks.forEach((tok, j) => {
      if (!tok || tok === "_") return;
      var id = moy(key) ? (/^c[a-z]{2,4}$/.test(tok) ? tok : null) : (/^[0-9a-z]{1,8}$/.test(tok) ? String(parseInt(tok, 36)) : null);
      if (j >= n || !id || !row(key, id)) dropped++;
      else if (!seen[id]) { seen[id] = 1; arr[j] = id; }
    });
    out[key] = arr;
  });
  return { ballots: out, dropped: dropped };
}

// mount and paint
function mount(panel, ctx) {
  cx = ctx; P = panel; S = ctx.state.season;
  if (!panel.getAttribute("data-awb")) { panel.setAttribute("data-awb", "1"); wire(panel); }
  var st = ctx.state, k0 = st.award && st.lg ? st.lg + "-" + st.award : null, c = load(S), d = ctx.docFor(S);
  if (KEYS.indexOf(k0) >= 0) ui.active = k0;
  if ((c && c.then) || (d && d.then)) {
    panel.innerHTML = ctx.controls("ballot") + ST("loading", "Loading the candidates.");
    Promise.all([c, d]).then(() => { if (ctx.live()) mount(panel, ctx); }, () => {
      if (ctx.live()) panel.innerHTML = ctx.controls("ballot") + ST("failed", "The candidates could not load. " + btn("retry", "Retry"));
    });
    return;
  }
  C = c; D = d; M = meta(); pv = {};
  if (!st.b) shared = null;
  else if (!shared || shared.b !== st.b) {
    var p = parse(st.b);
    shared = p && { b: st.b, season: S, ballots: p.ballots, dropped: p.dropped, ask: null, copied: [], fresh: true };
  }
  render();
}
function render() {
  var k = ui.active;
  bp = layoutKey();
  P.innerHTML = cx.controls("ballot") + `<div class="aw-b"><div id="aw-b-banner">${banner()}</div><div class="aw-b-grid"><div class="aw-b-left">` +
    `<div class="aw-b-chooser" id="aw-b-chooser" role="tablist" aria-label="Your ballots, ${S}">` + KEYS.map(x => {
      var on = x === k;
      return `<button role="tab" class="aw-b-chip${on ? " active" : ""}" id="aw-b-t${x}" aria-controls="aw-b-panel" aria-selected="${on}" ` +
        `tabindex="${on ? 0 : -1}" data-key="${x}">${lgOf(x)} ${FULL[awardOf(x)].replace(" of the Year", "")} <span></span></button>`;
    }).join("") + `</div><div class="aw-b-panel" id="aw-b-panel" role="tabpanel" tabindex="0" aria-labelledby="aw-b-t${k}"></div>` +
    `<div class="aw-b-actions">${btn("link", "Copy link") + btn("text", "Copy text") + (cx.gfx ? btn("img", "Save image") : "") + btn("clear", "Clear")}</div>` +
    '<div id="aw-b-confirm"></div><div id="aw-b-out"></div><p class="aw-b-save" id="aw-b-save"></p>' +
    '<p class="visually-hidden" id="aw-b-live" role="status" aria-live="polite"></p></div><div class="aw-b-right">' +
    (C.pools[k] ? '<div class="aw-b-find"><label id="aw-b-ql" for="aw-b-q"></label><div class="aw-b-qw"><input id="aw-b-q" type="text" ' +
      'role="combobox" aria-expanded="false" aria-controls="aw-b-list" aria-autocomplete="list" autocomplete="off" spellcheck="false" ' +
      `value="${esc(ui.q)}"><ul class="aw-b-list" id="aw-b-list" role="listbox" aria-label="Matching candidates" hidden></ul></div></div>` +
      filters() + '<div id="aw-b-strip"></div><p class="aw-b-count" id="aw-b-count" role="status"></p>' +
      '<p class="visually-hidden" id="aw-b-sortst" aria-live="polite"></p><div class="aw-b-tw" id="aw-b-tw">' +
      '<div class="aw-scroll aw-b-frame" id="aw-b-table"></div><div id="aw-b-drawer"></div></div>' : "") + "</div></div></div>";
  paintAll();
  paintNote();
  paintConfirm();
  var ch = el("chooser");
  ch.scrollLeft = el("t" + k).offsetLeft - ch.offsetLeft - 16;
  if (shared && shared.fresh && shared.season === S && el("shared")) { shared.fresh = false; el("shared").focus(); }
}
function layoutKey() { return (wide() ? "w" : "n") + (two() ? "2" : "1") + ":" + Math.round((P.clientWidth || 0) / 40); }
function paintAll() {
  KEYS.forEach(x => { var n = el("t" + x); if (n) n.lastChild.textContent = filled(slots(x)) + "/" + rule(awardOf(x)).n; });
  el("panel").innerHTML = slotsHTML();
  if (!C.pools[ui.active]) return;
  el("ql").textContent = qlabel();
  el("strip").innerHTML = strip();
  paintTable();
}
function paintNote() { var n = el("save"); if (n) n.textContent = storage === "ok" ? NOTE.ok + (cx.gfx ? " or save the image." : ".") : NOTE.no; }
function filters() {
  var k = ui.active, A = awardOf(k), h = '<div class="aw-b-filters">';
  if (A === "MVP") {
    h += '<div class="aw-b-seg" role="group" aria-label="Players shown">' + [["hit", "Hitters"], ["pit", "Pitchers"], ["all", "All"]]
      .map(x => btn("side", x[1], ` data-v="${x[0]}" aria-pressed="${ui.side === x[0]}"`)).join("") + "</div>";
  }
  if (A === "ROY") h += sw("every", ui.every, "Show every player");
  if (!moy(k)) h += `<label class="aw-b-chk"><input type="checkbox" data-act="floor"${floorOn(k) ? " checked" : ""}> Above the floor only</label>`;
  return h + sw("sel", store.showSelection, "Show the eephus selection") + "</div>";
}

// slots
function slotsHTML() {
  var k = ui.active, A = awardOf(k), R = rule(A), a = slots(k), t = esc(title(k)), h = `<h3 class="aw-b-h">Your ${t} ballot</h3>`;
  if (!C.pools[k]) return h + ST("unmeasured", esc(((D.rules || {})[A] || {}).blocked_on || `No candidates are on file for ${title(k)} in ${S}.`));
  h += `<ol class="aw-slots" aria-label="Your ${t} ballot, ${R.n} places">`;
  a.forEach((id, i) => {
    var lab = ord(i + 1) + DOT + R.points[i] + " pts", r = row(k, id), nm = r ? r.name : `Not on the ${S} candidate list`;
    var g = (act, off, l, glyph) => btn(act, `<span aria-hidden="true">${glyph}</span><span class="aw-b-tx">${l}</span>`,
      ` data-slot="${i}" aria-label="${esc(l + ", " + nm)}"${off ? ' aria-disabled="true"' : ""}`, "aw-b-ic");
    h += id == null ? `<li class="aw-b-slot is-empty" data-slot="${i}"><span class="aw-b-sl">${lab}</span>` +
      btn("choose", `Choose ${ord(i + 1)} place`, ` data-slot="${i}"`, "aw-b-choose") + "</li>"
      : `<li class="aw-b-slot" data-slot="${i}" data-id="${esc(id)}"><span class="aw-b-sl" aria-hidden="true">${lab}</span><div>` +
      `<span class="visually-hidden">${ord(i + 1)}, ${R.points[i]} points, </span>` +
      (r ? whoBtn(r, "slot") + sub([r.club, r.pos]) + `<span class="aw-b-kl">${esc(keyLine(k, r))}</span>` +
        notes(r).map(x => `<span class="aw-b-note">${x}</span>`).join("") : sub([nm])) +
      '</div><div class="aw-b-mv">' + g("up", i === 0, "Move up", "\u25b2") + g("down", i === a.length - 1, "Move down", "\u25bc") +
      g("rm", false, "Remove", "\u00d7") + "</div></li>";
  });
  return h + "</ol>" + (ui.drawer && ui.from === "slot" && !two() ? drawer() : "");
}
function whoBtn(r, from) { return `<button class="aw-b-who" data-act="drawer" data-from="${from}" data-id="${esc(r.id)}">${esc(r.name)}</button>`; }
function keyLine(k, r) {
  var cs = C.cols[awardOf(k)] || [], out = [];
  cs.forEach(c => { if (c.key === "score" && show(k, r, "score") != null) out.push(show(k, r, "score") + " " + c.label); });
  cs.some(c => {
    var ok = !FLAGS[c.key] && !TAIL[c.key] && c.key !== "score" && num(r.v[c.key]) != null;
    if (ok) out.push(show(k, r, c.key) + " " + c.label);
    return ok;
  });
  return out.join(DOT);
}
function notes(r) {
  var out = [];
  if (r.v.below_floor === true) out.push("Below the rule&#39;s playing-time floor.");
  if (r.out || r.v.outside_rookie_proxy === true) out.push("Outside the site&#39;s rookie test.");
  if (r.v.two_way === true) out.push("Two-way: batting and pitching shown.");
  return out;
}

// search
function target(a) { return ui.target != null && ui.target < a.length && a[ui.target] == null ? ui.target : a.indexOf(null); }
function qlabel() {
  var k = ui.active, t = target(slots(k));
  return "Find a " + who(k) + (t < 0 ? `, ${title(k)} (your ballot is full)` : ` for ${ord(t + 1)} place, ${title(k)}`);
}
function floorOn(k) { return k in ui.floor ? ui.floor[k] : /mvp|cy/.test(k); }
function poolRows(k) {
  var p = C.pools[k], A = awardOf(k), rs = A === "ROY" && ui.every ? p.rows.concat(p.out) : p.rows;
  return A === "MVP" && ui.side !== "all" ? rs.filter(r => r.v.two_way === true || (ui.side === "pit") === PIT.test(r.pos)) : rs;
}
function hit(r, q) {
  var n = norm(r.name);
  return norm(r.club).indexOf(q) === 0 || norm(r.pos).indexOf(q) === 0 || n.indexOf(q) === 0 ||
    n.split(/[^a-z0-9]+/).some(t => t && t.indexOf(q) === 0);
}
function results() {
  var q = norm(ui.q).trim(), rs = poolRows(ui.active).filter(r => !q || hit(r, q));
  var sn = r => q && norm(cx.surname(r.name)).indexOf(q) === 0 ? 0 : 1;
  rs.sort((a, b) => (sn(a) - sn(b)) || tie(a, b));
  return { list: rs.slice(0, 8), more: Math.max(0, rs.length - 8) };
}
function emptyMsg() { return ui.q ? `No eligible ${who(ui.active)} matches &quot;${esc(ui.q)}&quot;.` : "No player in this view clears the floor."; }
function paintList() {
  var inp = el("q"), ul = el("list");
  if (!inp) return;
  inp.setAttribute("aria-expanded", String(ui.list));
  ul.hidden = !ui.list;
  inp.removeAttribute("aria-activedescendant");
  if (!ui.list) return;
  var res = results(), k = ui.active, a = slots(k);
  ui.opt = Math.min(ui.opt, res.list.length - 1);
  ul.innerHTML = res.list.map((r, i) => {
    var at = a.indexOf(r.id);
    return `<li role="option" class="aw-b-opt" id="aw-b-o${i}" data-id="${esc(r.id)}" aria-selected="${i === ui.opt}">` +
      `<span class="aw-b-on">${esc(r.name)}</span> ${sub([r.club, r.pos])}<span class="aw-b-kl">${esc(keyLine(k, r))}</span>` +
      (at >= 0 ? sub(["On your ballot: " + ord(at + 1)]) : "") + "</li>";
  }).join("") + (res.more || !res.list.length ? '<li class="aw-b-more" role="presentation">' +
    (res.more ? `and ${res.more} more: keep typing` : emptyMsg()) + "</li>" : "");
  if (ui.opt < 0) return;
  inp.setAttribute("aria-activedescendant", "aw-b-o" + ui.opt);
  el("o" + ui.opt).scrollIntoView({ block: "nearest" });
}
function comboKey(e) {
  var n = results().list.length, dn = e.key === "ArrowDown";
  if (dn || e.key === "ArrowUp") {
    e.preventDefault();
    if (!ui.list || ui.opt < 0) { ui.list = true; ui.opt = n ? (dn ? 0 : n - 1) : -1; } else ui.opt = (ui.opt + (dn ? 1 : -1) + n) % n;
    paintList();
  } else if (e.key === "Enter") {
    var r = ui.list && results().list[ui.opt];
    if (r) { e.preventDefault(); add(r.id, "q"); }
  } else if (e.key === "Escape") {
    e.preventDefault();
    if (ui.list) { ui.list = false; paintList(); } else if (ui.q) { ui.q = e.target.value = ""; paintTable(); }
  }
}

// edits
function nameOf(k, id) { var r = row(k, id); return r ? r.name : "That entry"; }
function edited() { save(); paintAll(); }
function add(id, via) {
  var k = ui.active, a = slots(k), t = target(a), cur = a.indexOf(id), nm = nameOf(k, id), tt = title(k);
  if (cur >= 0 && (t < 0 || t === cur)) return say(`${nm} is already ${ord(cur + 1)} on your ${tt} ballot.`);
  if (t < 0) return say(`Your ${tt} ballot is full. Remove a name to add another.`);
  if (cur >= 0) a[cur] = null;
  a[t] = id;
  say(cur >= 0 ? `${nm} moved to ${ord(t + 1)}.` : `${nm} added to ${ord(t + 1)} on your ${tt} ballot.`);
  ui.target = null;
  if (via === "q") { ui.q = el("q").value = ""; ui.opt = -1; ui.list = false; }
  edited();
  paintList();
  focus(via === "q" ? "#aw-b-q" : `[data-act="add"][data-id="${id}"]`);
}
function move(i, d) {
  var k = ui.active, a = slots(k), j = i + d, id = a[i];
  if (id == null) return;
  if (j < 0 || j >= a.length) return say(`${nameOf(k, id)} is already ${ord(i + 1)}.`);
  a[i] = a[j]; a[j] = id;
  say(`${nameOf(k, id)} moved to ${ord(j + 1)}.`);
  edited();
  focus(`.aw-b-slot[data-slot="${j}"] [data-act="up"]`);
}
function remove(i) {
  var k = ui.active, a = slots(k), id = a[i];
  if (id == null) return;
  a[i] = null;
  if (ui.drawer === id) ui.drawer = null;
  say(nameOf(k, id) + " removed.");
  edited();
  focus(`.aw-b-slot[data-slot="${i}"] [data-act="choose"]`);
}
function setActive(k) {
  Object.assign(ui, { active: k, q: "", target: null, opt: -1, list: false, drawer: null, confirm: false });
  cx.setHash({ award: k.split("-")[1], lg: k.split("-")[0] });
  render();
  focus("#aw-b-t" + k);
}

// the comparison strip: the viewer's 1st to 3rd in lilac
function strip() {
  var k = ui.active, A = awardOf(k), rl = (D.rules || {})[A] || {}, sel = store.showSelection, a = slots(k);
  var b = !rl.blocked_on && D.awards && D.awards[A] && D.awards[A][lgOf(k)], mine = [0, 1, 2].map(i => row(k, a[i]));
  if (!b) return ST("unmeasured", esc(rl.blocked_on || "No comparison metrics are on file for this ballot."));
  var lab = wide() ? 110 : 56, nw = wide() ? 64 : 46;
  return cx.compare(D, A, lgOf(k), b, { id: "aw-b-cap", noRule: !sel, cap: `Your 1st to 3rd on each metric: ${title(k)}, ${S}`,
    G: { lab: lab, num: nw, trk: Math.max(96, Math.min(300, Math.floor((P.clientWidth || 358) - (two() ? 452 : 0) - lab - 3 * nw - 26))) },
    keys: '<p class="aw-b-keys"><span><span class="aw-b-sq" aria-hidden="true"></span>Lilac square: your 1st to 3rd</span>' +
      (sel ? '<span class="aw-b-sel"><span class="aw-b-ink" aria-hidden="true"></span>Ink box: ' +
        (D.status === "live" ? "the current leaders on the rule" : "the eephus selection") + ", 1st to 3rd</span>" : "") + "</p>",
    heads: mine.map((r, i) => ord(i + 1) + (r ? " " + (moy(k) ? r.club : cx.surname(r.name)) : "")),
    cell: (m, i) => mine[i] ? [mine[i].v[m.key], show(k, mine[i], m.key)] : [null, null],
    pts: m => mine.map((r, i) => {
      var v = r ? num(r.v[m.key]) : null;
      return v == null ? null : { n: i + 1, v: v, pc: pct(v, poolVals(k, m.key)) };
    }).filter(Boolean) });
}

// the candidate table, under the one sort contract
function tcols(k) {
  var cs = C.cols[awardOf(k)] || [], out = [{ key: "name", label: moy(k) ? "Club" : "Name" }, { key: "_slot", label: "Your slot" }];
  cs.forEach(c => { if (!FLAGS[c.key] && !TAIL[c.key]) out.push(c); });
  ["pa", "ip", "age"].forEach(x => cs.forEach(c => { if (c.key === x) out.push(c); }));
  if (store.showSelection) out.push({ key: "place", label: "Eephus place", sel: true });
  return out;
}
function sortOf(k) { return ui.sort[k] || { key: "score", asc: false }; }
function tie(a, b) {
  var x = num(a.v.score), y = num(b.v.score), p = norm(a.name), q = norm(b.name);
  if (x !== y) return x == null ? 1 : y == null ? -1 : y - x;
  return p < q ? -1 : p > q ? 1 : 0;
}
function tableRows(k) {
  var q = norm(ui.q).trim(), s = sortOf(k), a = slots(k), fl = floorOn(k);
  return poolRows(k).filter(r => (!fl || r.v.below_floor !== true) && (!q || hit(r, q))).map(r => {
    var i = a.indexOf(r.id);
    return [r, s.key === "_slot" ? (i < 0 ? null : i + 1) : s.key === "name" ? norm(r.name) : num(r.v[s.key])];
  }).sort((x, y) => {
    if (x[1] == null || y[1] == null) return (x[1] == null) === (y[1] == null) ? tie(x[0], y[0]) : (x[1] == null ? 1 : -1);
    return x[1] !== y[1] ? (x[1] < y[1] ? -1 : 1) * (s.asc ? 1 : -1) : tie(x[0], y[0]);
  }).map(x => x[0]);
}
function sortText(k) {
  var s = sortOf(k), lab = "";
  tcols(k).forEach(c => { if (c.key === s.key) lab = c.label; });
  return lab + ", " + (s.key === "name" ? (s.asc ? "A to Z" : "Z to A") : s.asc ? "lowest first" : "highest first");
}
function paintTable() {
  var k = ui.active, A = awardOf(k), frame = el("table"), cols = tcols(k), rs = tableRows(k), a = slots(k), s = sortOf(k);
  var inline = ui.drawer && ui.from === "table" && !two(), dw = Math.max(240, (frame.clientWidth || P.clientWidth || 358) - 2);
  el("count").textContent = `${rs.length} ${who(k)}s shown of ${poolRows(k).length}`;
  frame.innerHTML = !rs.length ? ST("empty", emptyMsg()) : `<table class="aw-b-tbl"><caption>${esc(S + " " + title(k) + " candidates, sorted by " +
    sortText(k))}</caption><thead><tr>` + cols.map(c => {
      var on = c.key === s.key;
      return '<th scope="col"' + (c.sel ? ` class="aw-b-sel" title="${esc("Where the site's rule places this " + who(k) + " on a full " +
        rule(A).n + "-place ballot.")}"` : "") + ` aria-sort="${on ? (s.asc ? "ascending" : "descending") : "none"}">` +
        `<button class="aw-b-sort" data-act="sort" data-k="${esc(c.key)}">${esc(c.label)}<span aria-hidden="true">` +
        (on ? (s.asc ? "\u25b2" : "\u25bc") : "") + "</span></button></th>";
    }).join("") + '<th scope="col">Add</th></tr></thead><tbody>' + rs.map(r => {
      var i = a.indexOf(r.id);
      return `<tr${i >= 0 ? ' class="is-mine"' : ""}><th scope="row">${whoBtn(r, "table")}${sub([moy(k) ? null : r.club, r.pos])}</th>` +
        cols.slice(1).map(c => {
          if (c.key === "_slot") return `<td>${i >= 0 ? ord(i + 1) : ""}</td>`;
          var cl = c.sel ? "aw-b-sel" : ink(r.v[c.key], famOf(c.key, A));
          return `<td${cl ? ` class="${cl}"` : ""}>${esc(show(k, r, c.key) || "")}</td>`;
        }).join("") + `<td>${btn("add", "Add", ` data-id="${esc(r.id)}" aria-label="${esc("Add " + r.name)}"`)}</td></tr>` +
        (inline && ui.drawer === r.id ? `<tr><td colspan="${cols.length + 1}"><div class="aw-b-sheet" style="width:${dw}px">${drawer()}</div></td></tr>` : "");
    }).join("") + "</tbody></table>";
  var html = ui.drawer && two() ? drawer() : "";
  el("drawer").innerHTML = html;
  el("tw").classList.toggle("has-drawer", !!html);
}
function sort(key) {
  var k = ui.active, s = sortOf(k), f = famOf(key, awardOf(k));
  var low = key === "name" || key === "_slot" || key === "place" || !!(f && T && T.LADDERS[f] && T.LADDERS[f].dir === "lo");
  ui.sort[k] = { key: key, asc: s.key === key ? !s.asc : low };
  paintTable();
  el("sortst").textContent = `Sorted by ${sortText(k)}.`;
  focus(`[data-act="sort"][data-k="${key}"]`);
}

// the player drawer
function drawer() {
  var k = ui.active, r = row(k, ui.drawer);
  if (!r) return "";
  var A = awardOf(k), t = M.top[k][r.id], tp = M.tpl, ln = [], id = moy(k) ? r.club : r.id;
  var race = D.race && D.race[A + "_" + lgOf(k)], f = race && race.weeks && (race.finalists || []).filter(x => String(x.id) === r.id)[0];
  var h = '<section class="aw-b-drawer" id="aw-b-dw" role="region" aria-labelledby="aw-b-dh" tabindex="-1"><div class="aw-b-dhd">' +
    `<h4 id="aw-b-dh">${esc(r.name)}</h4>${btn("dclose", "Close")}</div>` +
    sub([moy(k) ? null : r.club, r.pos, num(r.v.age) != null ? "age " + fmt(r.v.age, 0) : null]) +
    `<table class="aw-b-dt"><caption>Pool percentile among the ${moy(k) ? "clubs" : "candidates above the rule&#39;s floor"}.</caption>` +
    '<thead><tr><th scope="col">Metric</th><th scope="col">Value</th><th scope="col">Pool percentile</th></tr></thead><tbody>' +
    (C.cols[A] || []).filter(c => !FLAGS[c.key]).map(c => {
      var v = num(r.v[c.key]), p = c.key === "age" || (v === 0 && TAIL[c.key]) ? null : pct(v, poolVals(k, c.key));
      return `<tr><th scope="row">${esc(c.label)}</th><td class="${ink(v, famOf(c.key, A))}">${esc(show(k, r, c.key) || "-")}</td>` +
        `<td>${p == null ? "-" : p.toFixed(1)}</td></tr>`;
    }).join("") + "</tbody></table>";
  (moy(k) ? [["management", "In-Game Management"], ["franchise", "Franchise"]] : [["overview", "Player page"]]).forEach(x => {
    if (tp[x[0]]) ln.push([tp[x[0]].split("{id}").join(id), x[1]]);
  });
  if (t && t.links && t.links.prospx) ln.push([t.links.prospx, "PROSPX"]);
  if (ln.length) h += '<p class="aw-b-links">' + ln.map(x => `<a href="${esc(x[0])}">${esc(x[1])}</a>`).join(" ") + "</p>";
  if (f) {
    var pl = (race.places || {})[String(f.id)] || [], c = { 1: 0, 2: 0, 3: 0 }, n = 0;
    race.weeks.forEach((w, j) => { if ((race.missing || []).indexOf(w) < 0) { n++; if (c[pl[j]] != null) c[pl[j]]++; } });
    h += `<p class="aw-b-note">${esc(`The race: 1st in ${c[1]}, 2nd in ${c[2]}, 3rd in ${c[3]} of ${n} weeks on record. ` + (race.metric_label || ""))}</p>`;
  }
  return h + notes(r).concat(r.out && r.reason ? [esc("Rookie test: " + r.reason + ".")] : []).map(x => `<p class="aw-b-note">${x}</p>`).join("") +
    "</section>";
}
function openDrawer(id, from) {
  Object.assign(ui, { drawer: id, from: from });
  paintAll();
  var d = el("dw");
  if (d) { d.focus(); if (!two()) d.scrollIntoView({ block: "nearest" }); }
}
function closeDrawer() {
  var id = ui.drawer;
  ui.drawer = null;
  paintAll();
  focus(`[data-act="drawer"][data-from="${ui.from}"][data-id="${id}"]`);
}

// exports, clear and the shared banner
function clip(text, ok, what) {
  var fail = () => {
    el("out").innerHTML = `<label class="aw-b-outl">${what}<textarea readonly>${esc(text)}</textarea></label>`;
    var ta = el("out").querySelector("textarea");
    ta.focus();
    ta.select();
    say(`This browser did not allow copying. The ${what.toLowerCase()} is selected below.`);
  };
  try { navigator.clipboard.writeText(text).then(() => say(ok), fail); } catch (e) { fail(); }
}
function copyText() {
  var k = ui.active, lines = [`My ${S} ${title(k)} ballot`];
  slots(k).forEach((id, i) => { var r = row(k, id); if (id != null) lines.push((i + 1) + ". " + (r ? label(k, r) : id)); });
  if (lines.length === 1) return none();
  lines.push(url(enc(k)));
  clip(lines.join("\n"), "Ballot text copied.", "Ballot text");
}
function ask(q, yes, no, ys, ns) { return `<div class="aw-b-ask"><p>${esc(q)}</p>${btn(yes, ys) + btn(no, ns)}</div>`; }
function paintConfirm() { el("confirm").innerHTML = ui.confirm ? ask(`Clear your ${title(ui.active)} ballot?`, "clear-yes", "clear-no", "Clear", "Keep") : ""; }
function banner() {
  if (!shared || shared.season !== S) return "";
  var keys = KEYS.filter(k => has(shared.ballots[k])), n = shared.dropped;
  return '<section class="aw-b-banner" id="aw-b-shared" role="region" aria-labelledby="aw-b-sh" tabindex="-1">' +
    '<p class="aw-b-bh" id="aw-b-sh">You are viewing a shared ballot. It is not saved in this browser.</p>' +
    keys.map(k => `<div class="aw-b-sb"><p>${esc(title(k))}</p><ol>` + shared.ballots[k].map((id, i) => {
      var r = row(k, id);
      return r ? `<li value="${i + 1}">${esc(label(k, r))}</li>` : "";
    }).join("") + "</ol></div>").join("") +
    (n ? `<p>${n} ${n === 1 ? "name in this link is" : "names in this link are"} not on the ${S} candidate list and ${n === 1 ? "was" : "were"} left out.</p>` : "") +
    (shared.ask && shared.ask.length ? ask(`Replace your ${title(shared.ask[0])} ballot?`, "sh-yes", "sh-no", "Replace", "Keep mine") : "") +
    `<div class="aw-b-bact">${keys.length && !shared.ask ? btn("sh-copy", "Copy to my ballot") : ""}${btn("sh-close", "Close")}</div></section>`;
}
function put(k) {
  var a = slots(k), s = shared.ballots[k];
  for (var i = 0; i < a.length; i++) a[i] = s[i] == null ? null : s[i];
  shared.copied.push(title(k));
}
function sharedStep() {
  if (shared.ask.length) { el("banner").innerHTML = banner(); focus('[data-act="sh-yes"]'); return; }
  var done = shared.copied;
  save();
  shared = null;
  cx.setHash({ b: null });
  render();
  say(done.length ? `Copied to your ballot: ${done.join(", ")}.` : "Your ballots are unchanged.");
  focus("#aw-b-t" + ui.active);
}

// events
function sel(t) {
  store.showSelection = !store.showSelection;
  save();
  t.setAttribute("aria-checked", String(store.showSelection));
  el("strip").innerHTML = strip();
  paintTable();
}
var ACT = {
  choose: (t, i) => { Object.assign(ui, { target: i, list: true, opt: -1 }); el("ql").textContent = qlabel(); focus("#aw-b-q"); paintList(); },
  up: (t, i) => move(i, -1),
  down: (t, i) => move(i, 1),
  rm: (t, i) => remove(i),
  add: (t, i, id) => add(id, "table"),
  drawer: (t, i, id) => openDrawer(id, ga(t, "from")),
  dclose: closeDrawer,
  sort: t => sort(ga(t, "k")),
  side: t => {
    ui.side = ga(t, "v");
    P.querySelectorAll('[data-act="side"]').forEach(b => b.setAttribute("aria-pressed", String(b === t)));
    paintTable();
  },
  every: t => { ui.every = !ui.every; t.setAttribute("aria-checked", String(ui.every)); paintTable(); },
  sel: sel,
  link: () => { var b = enc(); if (b) clip(url(b), "Link copied.", "Link"); else say(`Your ${S} ballots are empty, so there is no link to copy.`); },
  text: copyText,
  img: t => has(slots(ui.active)) ? cx.share(S, ui.active, KEYS.map(k => [k, slots(k).map(id => (id = row(k, id)) && label(k, id))]),
    url(enc(ui.active)), url(enc()), t) : none(),
  clear: () => {
    if (!filled(slots(ui.active))) return none();
    ui.confirm = true; paintConfirm(); focus('[data-act="clear-yes"]');
  },
  "clear-no": () => { ui.confirm = false; paintConfirm(); focus('[data-act="clear"]'); },
  "clear-yes": () => {
    slots(ui.active).fill(null);
    ui.confirm = false; ui.drawer = null;
    paintConfirm();
    say(`Your ${title(ui.active)} ballot is cleared.`);
    edited();
    focus('.aw-b-slot[data-slot="0"] [data-act="choose"]');
  },
  "sh-copy": () => {
    shared.ask = [];
    KEYS.forEach(x => { if (has(shared.ballots[x])) { if (filled(slots(x))) shared.ask.push(x); else put(x); } });
    sharedStep();
  },
  "sh-yes": () => { put(shared.ask.shift()); sharedStep(); },
  "sh-no": () => { shared.ask.shift(); sharedStep(); },
  "sh-close": () => { shared = null; cx.setHash({ b: null }); el("banner").innerHTML = ""; focus("#aw-b-t" + ui.active); },
  retry: () => mount(P, cx)
};
function wire(p) {
  var keyMove = false;
  p.addEventListener("keydown", e => {
    var t = e.target, li = t.closest && t.closest(".aw-b-slot[data-id]");
    if (!t.closest) return;
    if (t.closest("#aw-b-chooser")) keyMove = /^(ArrowLeft|ArrowRight|Home|End)$/.test(e.key) && !e.altKey && !e.ctrlKey && !e.metaKey;
    if (t.id === "aw-b-q") comboKey(e);
    else if (li && e.altKey && (e.key === "ArrowUp" || e.key === "ArrowDown")) {
      e.preventDefault();
      move(+ga(li, "slot"), e.key === "ArrowUp" ? -1 : 1);
    } else if (e.key === "Escape" && ui.drawer && t.closest("#aw-b-dw")) closeDrawer();
  });
  p.addEventListener("focusin", e => {
    var t = e.target.closest && e.target.closest('#aw-b-chooser [role="tab"]');
    if (keyMove && t && t.getAttribute("aria-selected") !== "true") setActive(ga(t, "key"));
    keyMove = false;
  });
  p.addEventListener("mousedown", e => { if (e.target.closest && e.target.closest('[role="option"]')) e.preventDefault(); });
  p.addEventListener("input", e => {
    if (e.target.id !== "aw-b-q") return;
    Object.assign(ui, { q: e.target.value, opt: -1, list: true });
    paintList();
    paintTable();
  });
  p.addEventListener("change", e => { if (ga(e.target, "act") === "floor") { ui.floor[ui.active] = e.target.checked; paintTable(); } });
  p.addEventListener("focusout", e => {
    if (e.target.id === "aw-b-q") setTimeout(() => { if ((document.activeElement || {}).id !== "aw-b-q") { ui.list = false; paintList(); } }, 0);
  });
  p.addEventListener("click", e => {
    var t = e.target.closest && e.target.closest('[data-act], #aw-b-chooser [role="tab"], [role="option"]');
    if (!t || !p.contains(t)) return;
    if (t.getAttribute("role") === "tab") return setActive(ga(t, "key"));
    if (t.getAttribute("role") === "option") return add(ga(t, "id"), "q");
    var f = ACT[ga(t, "act")];
    if (f) f(t, +ga(t, "slot"), ga(t, "id"));
  });
  window.addEventListener("resize", () => {
    if (!C || !cx.live() || !el("panel")) return;
    clearTimeout(rt);
    rt = setTimeout(() => { if (layoutKey() !== bp) render(); }, 150);
  });
}

window.EephusAwardsBallot = { mount: mount };
})();
